# -*- coding: utf-8 -*-

"""
/***************************************************************************
 PlanoVoo
                                 A QGIS plugin
 PlanoVoo
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2024-11-05
        copyright            : (C) 2024 by Prof Cazaroli e Leandro França
        email                : contato@geoone.com.br
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

__author__ = 'Prof Cazaroli e Leandro França'
__date__ = '2024-11-05'
__copyright__ = '(C) 2024 by Prof Cazaroli e Leandro França'
__revision__ = '$Format:%H$'

from qgis.core import QgsProcessing, QgsProject, QgsProcessingAlgorithm, QgsWkbTypes, QgsVectorFileWriter, QgsProcessingParameterFolderDestination
from qgis.core import QgsProcessingParameterVectorLayer, QgsProcessingParameterNumber, QgsProcessingParameterString, QgsProcessingParameterFileDestination
from qgis.core import QgsTextFormat, QgsTextBufferSettings, QgsCoordinateReferenceSystem, QgsProperty
from qgis.core import QgsPalLayerSettings, QgsVectorLayerSimpleLabeling, QgsProcessingParameterBoolean, QgsCoordinateTransform
from qgis.core import QgsVectorLayer, QgsRasterLayer, QgsPoint, QgsPointXY, QgsField, QgsFields, QgsFeature, QgsGeometry
from qgis.core import QgsMarkerSymbol, QgsSingleSymbolRenderer, QgsSimpleLineSymbolLayer, QgsLineSymbol, QgsMarkerLineSymbolLayer
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QColor, QFont, QIcon
from PyQt5.QtCore import QVariant
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from .Funcs import obter_DEM, gerar_KML, gerar_CSV
import processing
import os
import math
import csv

# pontos_provider Air 2S (5472 × 3648)

class PlanoVoo_H(QgsProcessingAlgorithm):
    def initAlgorithm(self, config=None):
        diretorio = QgsProject.instance().homePath()

        dirArq = os.path.join(diretorio, 'api_key.txt') # Caminho do arquivo 'ali_key.txt' no mesmo diretório do projeto

        if os.path.exists(dirArq): # Verificar se o arquivo existe
            with open(dirArq, 'r') as file:    # Ler o conteúdo do arquivo (a chave da API)
                api_key = file.read().strip()  # Remover espaços extras no início e fim
        else:
            api_key = ''
        
        self.addParameter(QgsProcessingParameterVectorLayer('terreno', 'Terreno do Voo', types=[QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterVectorLayer('primeira_linha','Primeira Linha de Voo', types=[QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterNumber('h','Altura de Voo',
                                                       type=QgsProcessingParameterNumber.Double,
                                                       minValue=50,defaultValue=100))
        self.addParameter(QgsProcessingParameterNumber('dc','Tamanho do Sensor Horizontal (m)',
                                                       type=QgsProcessingParameterNumber.Double,
                                                       minValue=0,defaultValue=13.2e-3)) # igual p/o Phantom 4 Pro (5472 × 3648)
        self.addParameter(QgsProcessingParameterNumber('dl','Tamanho do Sensor Vertical (m)',
                                                       type=QgsProcessingParameterNumber.Double,
                                                       minValue=0,defaultValue=8.8e-3)) # igual p/o Phantom 4 Pro
        self.addParameter(QgsProcessingParameterNumber('f','Distância Focal (m)',
                                                       type=QgsProcessingParameterNumber.Double,
                                                       minValue=0,defaultValue=8.38e-3)) # Phantom 4 Pro é f = 9e-3
        self.addParameter(QgsProcessingParameterNumber('percL','Percentual de sobreposição Lateral (75% = 0.75)',
                                                       type=QgsProcessingParameterNumber.Double,
                                                       minValue=0.60,defaultValue=0.75))
        self.addParameter(QgsProcessingParameterNumber('percF','Percentual de sobreposição Frontal (85% = 0.85)',
                                                       type=QgsProcessingParameterNumber.Double,
                                                       minValue=0.60,defaultValue=0.85))
        self.addParameter(QgsProcessingParameterNumber('velocidade','Velocidade do Voo (m/s)',
                                                       type=QgsProcessingParameterNumber.Integer, minValue=2,defaultValue=8))
        self.addParameter(QgsProcessingParameterString('api_key', 'Chave API - OpenTopography',defaultValue=api_key))
        self.addParameter(QgsProcessingParameterFolderDestination('saida_kml', 'Pasta de Saída para o KML (Google Earth)'))
        self.addParameter(QgsProcessingParameterFileDestination('saida_csv', 'Arquivo de Saída CSV (Litchi)',
                                                               fileFilter='CSV files (*.csv)'))
        
    def processAlgorithm(self, parameters, context, feedback):
        teste = False # Quando True mostra camadas intermediárias
        
        # =====Parâmetros de entrada para variáveis==============================
        camada = self.parameterAsVectorLayer(parameters, 'terreno', context)
        crs = camada.crs()
        
        primeira_linha  = self.parameterAsVectorLayer(parameters, 'primeira_linha', context)

        apikey = parameters['api_key'] # 'd0fd2bf40aa8a6225e8cb6a4a1a5faf7' # Open Topgragraphy DEM Downloader

        H = parameters['h']
        dc = parameters['dc']
        dl = parameters['dl']
        f = parameters['f']
        percL = parameters['percL'] # Lateral
        percF = parameters['percF'] # Frontal
        velocidade = parameters['velocidade']
        
        caminho_kml = parameters['saida_kml']
        arquivo_csv = parameters['saida_csv']
        
        # =====Cálculo das Sobreposições=========================================
        # Distância das linhas de voo paralelas - Espaçamento Lateral
        tg_alfa_2 = dc / (2 * f)
        D_lat = dc * H / f
        SD_lat = percL * D_lat
        h1 = SD_lat / (2 * tg_alfa_2)
        deltaLat = SD_lat * (H / h1 - 1)

        # Espaçamento Frontal entre as fotografias- Espaçamento Frontal
        tg_alfa_2 = dl / (2 * f)
        D_front = dl * H / f
        SD_front = percF * D_front
        h1 = SD_front / (2 * tg_alfa_2)
        deltaFront = SD_front * (H / h1 - 1)
        
        feedback.pushInfo(f"Delta Lateral: {deltaLat}, Delta Frontal: {deltaFront}")
        
        # ===== Verificações =====================================================
        # Verificar se o polígono e a primeira_linha contém exatamente uma feature
        poligono_features = list(camada.getFeatures()) # dados do Terreno
        if len(poligono_features) != 1:
            raise ValueError("A camada deve conter somente um polígono.")

        poligono = poligono_features[0].geometry()
        vertices = [QgsPointXY(v) for v in poligono.vertices()] # Extrair os vértices do polígono
        
        linha_features = list(primeira_linha.getFeatures())
        if len(linha_features) != 1:
            raise ValueError("A camada primeira_linha deve conter somente uma linha.")

        # Verifica a geometria da primeira linha
        linha_geom = linha_features[0].geometry() # Obter a geometria da linha
        
        if linha_geom.asMultiPolyline():
            linha_vertices = linha_geom.asMultiPolyline()[0]  # Se a linha for do tipo poly
        else:
            linha_vertices = linha_geom.asPolyline() 
        
        # Criar a geometria da linha basee
        linha_base = QgsGeometry.fromPolylineXY([QgsPointXY(p) for p in linha_vertices])  

        # Verificar se a linha base coincide com um lado do polígono (até a segunda casa decimal)
        flag = False
        for i in range(len(vertices) - 1):
            # Criar a geometria do lado do polígono (em ambas as orientações)
            lado = QgsGeometry.fromPolylineXY([QgsPointXY(vertices[i]), QgsPointXY(vertices[i + 1])])
            lado_invertido = QgsGeometry.fromPolylineXY([QgsPointXY(vertices[i + 1]), QgsPointXY(vertices[i])])

            # Comparar se a geometria da linha base é igual ao lado (considerando a inversão também)
            if lado.equals(linha_base) or lado_invertido.equals(linha_base):
                flag = True
                break
            
        #feedback.pushInfo(f"Lado {i} - Ponto 1: ({vertices[i].x()}, {vertices[i].y()}) | Ponto 2: ({vertices[i + 1].x()}, {vertices[i + 1].y()})")
        #feedback.pushInfo(f"Linha base - Ponto 1: ({linha_vertices[0].x()}, {linha_vertices[0].y()}) | Ponto 2: ({linha_vertices[1].x()}, {linha_vertices[1].y()})")

        if not flag:
            raise ValueError("A camada primeira_linha deve ser um dos lados do terreno.")
        
        # =====================================================================
        # ===== OpenTopography ================================================
        
        # Obter a Altitude dos pontos das Fotos com OpenTopography
        feedback.pushInfo("Obtendo as Altitudes com o OpenTopography")
       
        # Reprojetar para WGS 84 (EPSG:4326), usado pelo OpenTopography
        crs_wgs = QgsCoordinateReferenceSystem(4326)
        transformador = QgsCoordinateTransform(crs, crs_wgs, QgsProject.instance())
        
        camadaMDE = obter_DEM("H", camada, transformador, apikey, feedback)
        
        QgsProject.instance().addMapLayer(camadaMDE)
        
        #camadaMDE = QgsProject.instance().mapLayersByName("DEM")[0]

        # =====================================================================
        # ===== Determinação das Linhas de Voo ================================
        
        # Encontrar os pontos extremos de cada lado da linha base (sempre terá 1 ou 2 pontos)
        ponto_extremo_dir = None
        ponto_extremo_esq = None
        dist_max_dir = 0 # float('-inf')
        dist_max_esq = 0 # float('-inf')

        # Iterar sobre os vértices do polígono
        ponto1 = QgsPointXY(linha_vertices[0])
        ponto2 = QgsPointXY(linha_vertices[1])

        for ponto_atual in vertices:
            # Calcular o produto vetorial para determinar se o ponto está à direita ou à esquerda
            produto_vetorial = (ponto2.x() - ponto1.x()) * (ponto_atual.y() - ponto1.y()) - (ponto2.y() - ponto1.y()) * (ponto_atual.x() - ponto1.x())

            # Calcular a distância perpendicular do ponto à linha base
            numerador = abs((ponto2.y() - ponto1.y()) * ponto_atual.x() - (ponto2.x() - ponto1.x()) * ponto_atual.y() + ponto2.x() * ponto1.y() - ponto2.y() * ponto1.x())
            denominador = math.sqrt((ponto2.y() - ponto1.y())**2 + (ponto2.x() - ponto1.x())**2)
            dist_perpendicular = numerador / denominador if denominador != 0 else 0

            # Atualizar o ponto extremo à direita (produto vetorial positivo)
            if produto_vetorial > 0 and dist_perpendicular > dist_max_dir:
                dist_max_dir = dist_perpendicular
                ponto_extremo_dir = ponto_atual

            # Atualizar o ponto extremo à esquerda (produto vetorial negativo)
            elif produto_vetorial < 0 and dist_perpendicular > dist_max_esq:
                dist_max_esq = dist_perpendicular
                ponto_extremo_esq = ponto_atual

        # Adicionar os pontos extremos encontrados à lista
        pontos_extremos = []
        if ponto_extremo_dir:
            pontos_extremos.append(ponto_extremo_dir)
        if ponto_extremo_esq:
            pontos_extremos.append(ponto_extremo_esq)

        # Criar camada temporária para o(s) ponto(s) oposto(s); a maioria das vezes será um ponto só
        pontosExtremos_layer = QgsVectorLayer('Point?crs=' + crs.authid(), 'Pontos Extremos', 'memory')
        pontos_provider = pontosExtremos_layer.dataProvider()
        pontos_provider.addAttributes([QgsField('id', QVariant.Int)])
        pontosExtremos_layer.updateFields()

        # Adicionar os pontos extremos à camada temporária
        for feature_id, ponto in enumerate(pontos_extremos, start=1):
            if ponto:
                ponto_feature = QgsFeature()
                ponto_feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(ponto)))
                ponto_feature.setAttributes([feature_id])  # ID do ponto
                pontos_provider.addFeature(ponto_feature)
        
        if teste == True:
            QgsProject.instance().addMapLayer(pontosExtremos_layer)
        
        # Criar uma linha estendida sobre a linha base
        
         # ponto inicial e final da linha base
        p1 = linha_vertices[0]
        p2 = linha_vertices[1]
        
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        angulo = math.atan2(dy, dx)
        
        extensao_x = (dist_max_esq + dist_max_dir) * math.cos(angulo)
        extensao_y = (dist_max_esq + dist_max_dir) * math.sin(angulo)

        p1_estendido = QgsPointXY(p1.x() - extensao_x ,p1.y() - extensao_y)
        p2_estendido = QgsPointXY(p2.x() + extensao_x ,p2.y() + extensao_y)
        linha_estendida = QgsGeometry.fromPolylineXY([QgsPointXY(p1_estendido), QgsPointXY(p2_estendido)])

        # Criar camada temporária para a linha estendida
        linhaEstendida_layer = QgsVectorLayer('LineString?crs=' + crs.authid(), 'Linha Estendida', 'memory')
        linha_provider = linhaEstendida_layer.dataProvider()
        linha_provider.addAttributes([QgsField('id', QVariant.Int)])
        linhaEstendida_layer.updateFields()

        linha_feature = QgsFeature()
        linha_feature.setGeometry(linha_estendida)
        linha_feature.setAttributes([1])  # ID da linha estendida
        linha_provider.addFeature(linha_feature)

        if teste == True:
            QgsProject.instance().addMapLayer(linhaEstendida_layer)
        
        # Criar linhas Paralelas à linha base até o(s) ponto(s) extremo(s)
        paralelas_layer = QgsVectorLayer('LineString?crs=' + crs.authid(), 'Linhas Paralelas', 'memory')
        paralelas_provider = paralelas_layer.dataProvider()
        paralelas_provider.addAttributes([QgsField('id', QVariant.Int)])
        paralelas_layer.updateFields()
        
        # Incluir a linha como a primeira linha paralela
        primeira_linha_feature = self.parameterAsVectorLayer(parameters, 'primeira_linha', context).getFeature(0)
        primeira_linha = primeira_linha_feature.geometry()       
        linha_id = 1
        paralela_feature = QgsFeature()
        paralela_feature.setGeometry(primeira_linha)
        paralela_feature.setAttributes([linha_id])
        paralelas_provider.addFeature(paralela_feature)

        pontos_extremos = []
        if ponto_extremo_dir:  # Se existe o ponto extremo à direita
            dist = linha_estendida.distance(QgsGeometry.fromPointXY(QgsPointXY(ponto_extremo_dir))) if ponto_extremo_dir else 0
            pontos_extremos.append((dist, 1))  # Distância e sentido para o ponto direito
            
        if ponto_extremo_esq:  # Se existe o ponto extremo à esquerda
            dist = linha_estendida.distance(QgsGeometry.fromPointXY(QgsPointXY(ponto_extremo_esq))) if ponto_extremo_esq else 0
            pontos_extremos.append((dist, -1))  # Distância e sentido para o ponto esquerdo

        # Criar as paralelas em um sentido de cada vez
        for dist, sentido in pontos_extremos:
            deslocamento = deltaLat * sentido  # Usando a direção positiva ou negativa
            
            while abs(deslocamento) <= dist:  # Criar linhas paralelas até o ponto extremo
                linha_id += 1

                # Deslocamento da linha base para criar a paralela
                parameters = {
                    'INPUT': linhaEstendida_layer,  # Linha base
                    'DISTANCE': deslocamento,
                    'OUTPUT': 'memory:'
                }

                result = processing.run("native:offsetline", parameters)
                linha_paralela_layer = result['OUTPUT']
                
                # Obter a geometria da linha paralela
                feature = next(linha_paralela_layer.getFeatures(), None)
                linha_geom = feature.geometry() if feature else None

                if linha_geom:
                    # Interseção da linha paralela com o polígono
                    intersecao_geom = linha_geom.intersection(poligono)

                    # Adicionar a paralela à camada
                    paralela_feature = QgsFeature()
                    paralela_feature.setGeometry(intersecao_geom)
                    paralela_feature.setAttributes([linha_id])
                    paralelas_provider.addFeature(paralela_feature)
                    paralelas_layer.updateExtents()

                    # Atualizar a linha base para a próxima paralela
                    linha_estendida = linha_paralela_layer

                    deslocamento += deltaLat * sentido  # Atualizar o deslocamento
              
        if teste == True:
            QgsProject.instance().addMapLayer(paralelas_layer)

        # Criar a camada com a união das linhas paralelas
        linhas_layer = QgsVectorLayer('LineString?crs=' + crs.authid(), 'Linhas', 'memory')
        linhas_provider = linhas_layer.dataProvider()
        linhas_provider.addAttributes([QgsField('id', QVariant.Int)])
        linhas_layer.updateFields()
        
        paralelas_features = list(paralelas_layer.getFeatures())
        linha_id = 1
        
        for i in range(len(paralelas_features)):
            # Adicionar a linha paralela à camada
            linha_paralela = paralelas_features[i]
            linha_paralela.setAttributes([linha_id])
            linhas_provider.addFeature(linha_paralela)
            linha_id += 1

            # Criar a linha de costura
            if i < len(paralelas_features) - 1:
                geom_atual = paralelas_features[i].geometry()
                geom_seguinte = paralelas_features[i + 1].geometry()

                # Obter os extremos das linhas (direita ou esquerda alternando)
                extremos_atual = list(geom_atual.vertices())
                extremos_seguinte = list(geom_seguinte.vertices())

                if i % 2 == 0:  # Conecta pelo lado direito
                    ponto_inicio = QgsPointXY(extremos_atual[-1])  # Extremo final da linha atual
                    ponto_fim = QgsPointXY(extremos_seguinte[-1])  # Extremo final da próxima linha
                else:  # Conecta pelo lado esquerdo
                    ponto_inicio = QgsPointXY(extremos_atual[0])  # Extremo inicial da linha atual
                    ponto_fim = QgsPointXY(extremos_seguinte[0])  # Extremo inicial da próxima linha
                
                # Criar a geometria da linha de costura
                conexao_geom = QgsGeometry.fromPolylineXY([ponto_inicio, ponto_fim])
                conexao_feature = QgsFeature()
                conexao_feature.setGeometry(conexao_geom)
                conexao_feature.setAttributes([linha_id])
                linhas_provider.addFeature(conexao_feature)

                linha_id += 1

        # Atualizar extensão da camada de resultado
        linhas_layer.updateExtents()
      
        # Verificar se as linhas estão contínuas
        linhas = sorted(linhas_layer.getFeatures(), key=lambda f: f['id'])
        
        for i in range(len(linhas) - 1):
            geom_atual = linhas[i].geometry()
            geom_seguinte = linhas[i + 1].geometry()
        
            # Obter os extremos das linhas (direita ou esquerda alternando)
            extremos_atual = list(geom_atual.vertices())
            extremos_seguinte = list(geom_seguinte.vertices())
        
            ponto_final_atual = QgsPointXY(extremos_atual[-1].x(), extremos_atual[-1].y())  # Extremo final da linha atual
            ponto_inicial_seguinte = QgsPointXY(extremos_seguinte[0].x(), extremos_seguinte[0].y())  # Extremo inicial da próxima linha

            if ponto_final_atual != ponto_inicial_seguinte: # se for igual continua para a próxima linha
                extremos_seguinte = [QgsPointXY(p.x(), p.y()) for p in reversed(extremos_seguinte)] # Invertemos os vértices da linha seguinte
                geom_seguinte = QgsGeometry.fromPolylineXY(extremos_seguinte)

                # Atualizar imediatamente a geometria da linha na camada
                linhas_layer.dataProvider().changeGeometryValues({linhas[i + 1].id(): geom_seguinte})

                # Atualizar a linha seguinte na lista local para manter consistência no loop
                linhas[i + 1].setGeometry(geom_seguinte)
        
        # Atualizar a extensão da camada
        linhas_layer.updateExtents()

        if teste == True:
            QgsProject.instance().addMapLayer(linhas_layer)
        
        # Criação de uma linha única para Linha de Voo
        linha_voo_layer = QgsVectorLayer('LineString?crs=' + crs.authid(), 'Linha de Voo', 'memory')
        linha_voo_provider = linha_voo_layer.dataProvider()
        linha_voo_provider.addAttributes([QgsField('id', QVariant.Int)])
        linha_voo_provider.addAttributes([QgsField('alturavoo', QVariant.Double)])
        linha_voo_layer.updateFields()

        # Obter e ordenar as feições pela ordem dos IDs para garantir
        linhas = sorted(linhas_layer.getFeatures(), key=lambda f: f['id'])

        # Iniciar a lista de coordenadas para a linha única
        linha_unica_coords = []

        # Adicionar coordenadas de todas as linhas em ordem
        for f in linhas:
            geom = f.geometry()
            if geom.isMultipart():
                partes = geom.asMultiPolyline()
                for parte in partes:
                    linha_unica_coords.extend(parte)  # Adicionar todas as partes
            else:
                linha_unica_coords.extend(geom.asPolyline())  # Adicionar a linha simples
            
        # Criar a geometria combinada a partir das coordenadas coletadas
        linha_unica_geom = QgsGeometry.fromPolylineXY(linha_unica_coords)

        # Criar a feature para a linha única
        linha_unica_feature = QgsFeature()
        linha_unica_feature.setGeometry(linha_unica_geom)
        linha_unica_feature.setAttributes([1])  # Atributo ID = 1

        # Adicionar a feature à camada de linha de voo
        linha_voo_provider.addFeature(linha_unica_feature)

        # Atualizar extensão da camada de resultado
        linha_voo_layer.updateExtents()
        
        # =====================================================================
        # =====Criar a camada Pontos de Fotos==================================
        
        # Criar uma camada Ponto com os deltaFront sobre a linha
        pontos_fotos = QgsVectorLayer('Point?crs=' + crs.authid(), 'Pontos Fotos', 'memory')
        pontos_provider = pontos_fotos.dataProvider()

        # Definir campos
        campos = QgsFields()
        campos.append(QgsField("id", QVariant.Int))
        campos.append(QgsField("latitude", QVariant.Double))
        campos.append(QgsField("longitude", QVariant.Double))
        pontos_provider.addAttributes(campos)
        pontos_fotos.updateFields()

        linha_voo = next(linha_voo_layer.getFeatures())  # Pegando a única linha
        geom_linha = linha_voo.geometry() # Obter a geometria da linha

        # Obter a geometria do polígono a partir da camada
        poligono_feature = next(camada.getFeatures())  # Assumindo que a camada contém apenas um polígono
        poligono_geom = poligono_feature.geometry()  # Geometria do polígono

        # Criar um buffer com tolerância de 3 metros
        tolerancia = 3  # Margem de 3 metros
        poligono_com_tolerancia = poligono_geom.buffer(tolerancia, 5)  # Buffer com 5 segmentos por quadrante

        # Obter o ponto inicial da linha
        ponto_inicial = QgsPointXY(geom_linha.vertexAt(0))

        # Gerar pontos
        pontoID = 1
        distVoo = geom_linha.length()
        distAtual = 0
        
        # Primeiro Ponto no início da primeira linha da Linha de Voo
        ponto_feature = QgsFeature()
        ponto_feature.setFields(campos)
        ponto_feature.setAttribute("id", pontoID)
        ponto_feature.setAttribute("latitude", ponto_inicial.y())
        ponto_feature.setAttribute("longitude", ponto_inicial.x())
        ponto_feature.setGeometry(QgsGeometry.fromPointXY(ponto_inicial))
        pontos_provider.addFeature(ponto_feature)
        
        pontoID += 1

        while True:
            distAtual += deltaFront
            
            if distAtual > (distVoo):  # Evitar extrapolação além do comprimento da linha
                feedback.pushInfo(f"Dist. Atual: {distAtual}, Dist. Voo: {distVoo}")
                break
            
            ponto = geom_linha.interpolate(distAtual).asPoint()
            ponto_geom = QgsGeometry.fromPointXY(QgsPointXY(ponto))
            
            # Adicionar ponto somente se estiver dentro do polígono
            if poligono_com_tolerancia.contains(ponto_geom):
                ponto_feature = QgsFeature()
                ponto_feature.setFields(campos)
                ponto_feature.setAttribute("id", pontoID)
                ponto_feature.setAttribute("latitude", ponto.y())
                ponto_feature.setAttribute("longitude", ponto.x())
                ponto_feature.setGeometry(ponto_geom)
                pontos_provider.addFeature(ponto_feature)
                
                pontoID += 1

        # Atualizar a camada
        pontos_fotos.updateExtents()

        # Obter a altitude dos pontos das Fotos
        prov = pontos_fotos.dataProvider()
        pontos_fotos.startEditing()
        
        # Adicionar um campo para Altura do Voo, se não existir
        if 'alturaVoo' not in [field.name() for field in prov.fields()]:
            prov.addAttributes([QgsField('alturaVoo', QVariant.Double)])
            pontos_fotos.updateFields()

        # definir o valor de Z
        for f in pontos_fotos.getFeatures():
            point = f.geometry().asPoint()
            
            # Transformar coordenada para CRS do raster
            point_wgs = transformador.transform(QgsPointXY(point.x(), point.y()))
            
            # Obter o valor de Z do MDE
            value, result = camadaMDE.dataProvider().sample(point_wgs, 1)  # Resolução = 1
            if result:
                f['alturaVoo'] = value + H  # altura de Voo
                pontos_fotos.updateFeature(f)

        pontos_fotos.commitChanges()

        # Point para PointZ
        result = processing.run("native:setzvalue", 
                                {'INPUT':pontos_fotos,
                                 'Z_VALUE':QgsProperty.fromExpression('"altitude"'),
                                 'OUTPUT':'TEMPORARY_OUTPUT'})
        pontos_fotos = result['OUTPUT']
        pontos_fotos.setName("Pontos Fotos") # Para que nao fique no QGIS com o nome 'Z adicionado'

        # Simbologia
        simbolo = QgsMarkerSymbol.createSimple({'color': 'blue', 'size': '3'})
        renderer = QgsSingleSymbolRenderer(simbolo)
        pontos_fotos.setRenderer(renderer)

        # Rótulos
        settings = QgsPalLayerSettings()
        settings.fieldName = "id"
        settings.isExpression = True
        settings.enabled = True

        textoF = QgsTextFormat()
        textoF.setFont(QFont("Arial", 10, QFont.Bold))
        textoF.setSize(10)

        bufferS = QgsTextBufferSettings()
        bufferS.setEnabled(True)
        bufferS.setSize(1)  # Tamanho do buffer em milímetros
        bufferS.setColor(QColor("white"))  # Cor do buffer

        textoF.setBuffer(bufferS)
        settings.setFormat(textoF)

        pontos_fotos.setLabelsEnabled(True)
        pontos_fotos.setLabeling(QgsVectorLayerSimpleLabeling(settings))

        pontos_fotos.triggerRepaint()

        #QgsProject.instance().addMapLayer(camadaMDE)
        QgsProject.instance().addMapLayer(pontos_fotos)
        
        feedback.pushInfo("")
        feedback.pushInfo("Linha de Voo e Pontos para Fotos concluídos com sucesso!")
        
        #pontos_fotos = QgsProject.instance().mapLayersByName("Pontos Fotos")[0]
        
        # Reprojetar camada Pontos Fotos de UTM para WGS84 (4326)
        pontos_reproj = QgsVectorLayer('Point?crs=' + crs_wgs.authid(), 'Pontos Reprojetados', 'memory') 
        pontos_reproj.startEditing()
        pontos_reproj.dataProvider().addAttributes(pontos_fotos.fields())
        pontos_reproj.updateFields()

        # Reprojetar os pontos
        for f in pontos_fotos.getFeatures():
            geom = f.geometry()
            geom.transform(transformador)
            reproj = QgsFeature()
            reproj.setGeometry(geom)
            reproj.setAttributes(f.attributes())
            pontos_reproj.addFeature(reproj)

        pontos_reproj.commitChanges()
        
        # Point para PointZ
        result = processing.run("native:setzvalue", 
                                {'INPUT':pontos_reproj,
                                 'Z_VALUE':QgsProperty.fromExpression('"altitude"'),
                                 'OUTPUT':'TEMPORARY_OUTPUT'})
        pontos_reproj = result['OUTPUT']
        pontos_reproj.setName("Pontos Reprojetados") # Para que nao fique no QGIS com o nome 'Z adicionado'
        
        if teste == True:
            QgsProject.instance().addMapLayer(pontos_reproj)
            
        # ====== Ponto Z na Linha de Voo ====================================================
        
        # Obter a altura mais alta de 'pontos_fotos'
        maior_altura = None

        for f in pontos_fotos.getFeatures():
            # Obter o valor de 'alturavoo' para cada ponto
            alturavoo = f['alturavoo']
            
            # Atualizar a maior altura, se necessário
            if maior_altura is None or alturavoo > maior_altura:
                maior_altura = alturavoo
        
        linha_voo_layer.startEditing()
        
        for f in linha_voo_layer.getFeatures():
            f['alturavoo'] = maior_altura
            linha_voo_layer.updateFeature(f)
        
        linha_voo_layer.commitChanges()

        # LineString para PointZ
        result = processing.run("native:setzvalue", 
                                {'INPUT':linha_voo_layer,
                                 'Z_VALUE':QgsProperty.fromExpression('"alturavoo"'),
                                 'OUTPUT':'TEMPORARY_OUTPUT'})
        linha_voo_layer = result['OUTPUT']
        linha_voo_layer.setName("Linha de Voo") # Para que nao fique no QGIS com o nome 'Z adicionado' 
        
        # Configurar simbologia de seta
        line_symbol = QgsLineSymbol.createSimple({'color': 'blue', 'width': '0.3'})  # Linha base

        seta = QgsMarkerSymbol.createSimple({'name': 'arrow', 'size': '5', 'color': 'blue', 'angle': '90'})

        marcador = QgsMarkerLineSymbolLayer()
        marcador.setInterval(30)  # Define o intervalo entre as setas (marcadores)
        marcador.setSubSymbol(seta)
        linha_voo_layer.renderer().symbol().appendSymbolLayer(marcador)
        
        QgsProject.instance().addMapLayer(linha_voo_layer)
        
        # Reprojetar a única linha da camada linha_voo_layer para WGS84 (4326)
        linha_voo_reproj = QgsVectorLayer('LineString?crs=' + crs_wgs.authid(), 'Linha de Voo Reprojetada', 'memory')
        linha_voo_reproj.startEditing()
        linha_voo_reproj.dataProvider().addAttributes(linha_voo_layer.fields())
        linha_voo_reproj.updateFields()

        # Obter a única linha da camada linha_voo_layer e reprojetar
        linha_voo_feature = next(linha_voo_layer.getFeatures(), None)  # Obter a primeira (e única) linha
        if linha_voo_feature:
            geom = linha_voo_feature.geometry()
            geom.transform(transformador)  # Transformar a geometria para o CRS de destino
            reproj = QgsFeature()
            reproj.setGeometry(geom)
            reproj.setAttributes(linha_voo_feature.attributes())
            linha_voo_reproj.addFeature(reproj)

        linha_voo_reproj.commitChanges()
        
        # LineString para PointZ
        result = processing.run("native:setzvalue", 
                                {'INPUT':linha_voo_reproj,
                                 'Z_VALUE':QgsProperty.fromExpression('"altitude"'),
                                 'OUTPUT':'TEMPORARY_OUTPUT'})
        linha_voo_reproj = result['OUTPUT']
        linha_voo_reproj.setName("Linha de Voo Reprojetada") # Para que nao fique no QGIS com o nome 'Z adicionado'
        
        if teste == True:
            QgsProject.instance().addMapLayer(linha_voo_reproj)
        
        # =========Exportar para o Google  E a r t h   P r o  (kml)================================================
        
        if caminho_kml: # Verificar se o caminho KML está preenchido 
            arquivo_kml = caminho_kml + r"\Pontos Fotos.kml"
            gerar_KML(pontos_reproj, arquivo_kml, nome="Pontos Fotos", crs_wgs, feedback=feedback)
            
            arquivo_kml = caminho_kml + r"\Linha de Voo.kml"
            gerar_KML(linha_voo_reproj, arquivo_kml, nome="Linha de Voo", crs_wgs, feedback=feedback)
        else:
            feedback.pushInfo("Caminho KML não especificado. Etapa de exportação ignorada.")
            
        # =============L I T C H I==========================================================

        if arquivo_csv and arquivo_csv.endswith('.csv'): # Verificar se o caminho CSV está preenchido
            gerar_CSV("H", pontos_reproj, arquivo_csv, velocidade, deltaFront, angulo=0, H, feedback=feedback)
        else:
            feedback.pushInfo("Caminho CSV não especificado. Etapa de exportação ignorada.")

        # Mensagem de Encerramento
        feedback.pushInfo("")
        feedback.pushInfo("Plano de Voo Horizontal executado com sucesso.") 
            
        return {}
        
    def name(self):
        return 'PlanoVooH'.lower()

    def displayName(self):
        return self.tr('Pontos Fotos - Voo Horizontal')

    def group(self):
        return self.tr(self.groupId())

    def groupId(self):
        return ''
        
    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return PlanoVoo_H()
    
    def tags(self):
        return self.tr('Flight Plan,Measure,Topography').split(',')
    
    def icon(self):
        return QIcon(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'images/PlanoVoo.png'))
    
    texto = "Este algoritmo calcula a sobreposição lateral e frontal de Voo de Drone, \
            fornecendo uma camada da 'Linha do Voo' e uma camada dos 'Pontos' para Fotos. \
            Gera ainda: a planilha CSV para importar no Litchi e o arquivo KML para Google Earth. \
            Se você usa um aplicativo para Voo que não seja o Litchi, pode usar os pontos gerados no QGIS."
    figura = 'images/PlanoVoo1.jpg'

    def shortHelpString(self):
        corpo = '''<div align="center">
                      <img src="'''+ os.path.join(os.path.dirname(os.path.dirname(__file__)), self.figura) +'''">
                      </div>
                      <div align="right">
                      <p align="right">
                      <b>'Autor: Prof Cazaroli     -     Leandro França'</b>
                      </p>'Geoone'</div>
                    </div>'''
        return self.tr(self.texto) + corpo
