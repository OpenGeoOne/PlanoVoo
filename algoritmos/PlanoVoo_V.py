# -*- coding: utf-8 -*-

"""
/***************************************************************************
 PlanoVoo
                                 A QGIS plugin
 PlanoVoo
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2024-12-02
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

from qgis.core import QgsProcessing, QgsProject, QgsProcessingAlgorithm, QgsWkbTypes, QgsVectorFileWriter
from qgis.core import QgsProcessingParameterVectorLayer, QgsProcessingParameterNumber, QgsProcessingParameterString
from qgis.core import QgsTextFormat, QgsTextBufferSettings, QgsProcessingParameterFileDestination, QgsCoordinateReferenceSystem
from qgis.core import QgsPalLayerSettings, QgsVectorLayerSimpleLabeling, QgsProcessingParameterBoolean, QgsCoordinateTransform
from qgis.core import QgsVectorLayer, QgsRasterLayer, QgsPoint, QgsPointXY, QgsField, QgsFields, QgsFeature, QgsGeometry
from qgis.core import QgsMarkerSymbol, QgsSingleSymbolRenderer, QgsSimpleLineSymbolLayer, QgsLineSymbol, QgsMarkerLineSymbolLayer
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QColor, QFont, QIcon
from PyQt5.QtCore import QVariant
from qgis.PyQt.QtWidgets import QAction, QMessageBox
import processing
import os
import math
import csv

# pontos_provider Air 2S (5472 × 3648)

class PlanoVoo_V(QgsProcessingAlgorithm):
    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer('linha_base','Linha Base de Voo', types=[QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterNumber('altura','Altura do Objeto (m)',
                                                       type=QgsProcessingParameterNumber.Double, minValue=2,defaultValue=15))
        self.addParameter(QgsProcessingParameterNumber('alturaMin','Altura Inicial (m)',
                                                       type=QgsProcessingParameterNumber.Double, minValue=2,defaultValue=2))
        self.addParameter(QgsProcessingParameterNumber('deltaHorizontal','Espaçamento Horizontal (m)',
                                                       type=QgsProcessingParameterNumber.Double, minValue=2,defaultValue=5))
        self.addParameter(QgsProcessingParameterNumber('deltaVertical','Espaçamento Vertical (m)',
                                                       type=QgsProcessingParameterNumber.Double, minValue=2,defaultValue=3)) 
        self.addParameter(QgsProcessingParameterString('api_key', 'Chave API - OpenTopography',defaultValue='d0fd2bf40aa8a6225e8cb6a4a1a5faf7'))
        self.addParameter(QgsProcessingParameterFileDestination('saida_csv', 'Arquivo de Saída CSV para o Litchi',
                                                               fileFilter='CSV files (*.csv)'))
        self.addParameter(QgsProcessingParameterFileDestination('saida_kml', 'Arquivo de Saída KML para o Google Earth',
                                                               fileFilter='KML files (*.kml)'))
        
    def processAlgorithm(self, parameters, context, feedback):
        teste = True # Quando True mostra camadas intermediárias
        
        # =====Parâmetros de entrada para variáveis========================
        linha_base = self.parameterAsVectorLayer(parameters, 'linha_base', context)
        crs = linha_base.crs()

        H = parameters['altura']
        h = parameters['alturaMin']
        deltaH = parameters['deltaHorizontal']
        deltaV = parameters['deltaVertical']
        
        apikey = parameters['api_key'] # 'd0fd2bf40aa8a6225e8cb6a4a1a5faf7' # Open Topgragraphy DEM Downloader
        
        caminho_kml = parameters['saida_kml']
        caminho_csv = parameters['saida_csv']
        
        feedback.pushInfo(f"Altura: {H}, Delta Horizontal: {deltaH}, Delta Vertical: {deltaV}")
        
        # =====================================================================
        # ===== Determinação das Linhas de Voo ================================
        
        # Verificar se a linha_base contém apenas uma feature
        linha = list(linha_base.getFeatures())
        if len(linha) != 1:
            raise ValueError("A camada Linha Base deve conter somente uma linha.")
        
        linha_geom = linha[0].geometry()  # Obter a geometria da linha base
        
        # Verificar se delatH é mútiplo do comprimento da Linha Base
        comprimento = linha_geom.length()
        margem = 1  # margem de 1 metro
        restante = comprimento % deltaH

        if restante > margem:
            raise ValueError(f"O espaçamento horizontal ({deltaH}) não é múltiplo do comprimento total da Linha Base ({comprimento}).")
        
        # Criar linhas Paralelas à linha base
        paralelas_layer = QgsVectorLayer('LineString?crs=' + crs.authid(), 'Linhas Paralelas', 'memory')
        paralelas_provider = paralelas_layer.dataProvider()
        paralelas_provider.addAttributes([
                    QgsField('id', QVariant.Int),
                    QgsField('altura', QVariant.Double)
                ])
        paralelas_layer.updateFields()
        
        linha_id = 1
        deslocamento = h
        
        # Criar linhas paralelas até atingir a altura H
        while deslocamento <= H + 3:
            parameters = {
                'INPUT': linha_base,  # Linha base
                'DISTANCE': deslocamento,
                'OUTPUT': 'memory:'
            }

            result = processing.run("native:offsetline", parameters)
            linha_paralela_layer = result['OUTPUT']
            
            # Obter a geometria da linha paralela
            feature = next(linha_paralela_layer.getFeatures(), None)
            linha_geom = feature.geometry() if feature else None

            # Adicionar a paralela à camada
            paralela = QgsFeature()
            paralela.setGeometry(linha_geom)
            paralela.setAttributes([linha_id, deslocamento])
            paralelas_provider.addFeature(paralela)

            linha_id += 1
            deslocamento += deltaV
        
        paralelas_layer.updateExtents()
        
        if teste == True:
            QgsProject.instance().addMapLayer(paralelas_layer)
        
        # Verificar se existem pelo menos duas linhas na camada paralelas_layer
        if paralelas_layer.featureCount() < 2:
            feedback.reportError("É necessário pelo menos duas linhas paralelas para criar as costuras.")
        else:
            # Obter todas as linhas paralelas ordenadas por ID
            linhas = list(paralelas_layer.getFeatures())
            linhas.sort(key=lambda f: f['id'])  # Ordenar pelo atributo 'id'
            
            # Lista para armazenar todos os vértices em sequência
            vertices_continuos = []

            alternar_lado = True  # Alternar entre finais e inícios para adicionar os vértices

            for i, linha_feature in enumerate(linhas):
                geom = linha_feature.geometry()

                if not geom or geom.isEmpty():
                    continue  # Ignorar geometrias inválidas

                vertices = geom.asPolyline()
                if not vertices:
                    continue  # Ignorar linhas sem vértices

                if i == 0:
                    # Adicionar todos os vértices da primeira linha (início ao fim)
                    vertices_continuos.extend(vertices)
                else:
                    if alternar_lado:
                        # Adicionar os vértices em ordem reversa (da próxima linha ou costura)
                        vertices_continuos.extend(vertices[::-1])
                    else:
                        # Adicionar os vértices em ordem direta
                        vertices_continuos.extend(vertices)

                    alternar_lado = not alternar_lado  # Alternar o sentido para a próxima linha ou costura

            # Criar a nova linha unificada
            linha_unica_geom = QgsGeometry.fromPolylineXY(vertices_continuos)

            # Adicionar a linha unificada em uma nova camada de memória
            linha_voo = QgsVectorLayer('LineString?crs=' + paralelas_layer.crs().authid(), 'Linha de Voo', 'memory')
            linha_unica_provider = linha_voo.dataProvider()

            # Criar a nova feature com a linha unificada
            linha_unica_feature = QgsFeature()
            linha_unica_feature.setGeometry(linha_unica_geom)
            linha_unica_provider.addFeature(linha_unica_feature)

            linha_voo.updateExtents()

        # Adicionar a camada ao projeto
        QgsProject.instance().addMapLayer(linha_voo)
        
        # Configurar simbologia de seta
        line_symbol = QgsLineSymbol.createSimple({'color': 'blue', 'width': '0.3'})  # Linha base

        seta = QgsMarkerSymbol.createSimple({'name': 'arrow', 'size': '5', 'color': 'blue', 'angle': '90'})

        marcador = QgsMarkerLineSymbolLayer()
        marcador.setInterval(30)  # Define o intervalo entre as setas (marcadores)
        marcador.setSubSymbol(seta)
        linha_voo.renderer().symbol().appendSymbolLayer(marcador)
        
        QgsProject.instance().addMapLayer(linha_voo)
        
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
        campos.append(QgsField("altitude", QVariant.Double))
        pontos_provider.addAttributes(campos)
        pontos_fotos.updateFields()
        
        pontoID = 1
        
        # Criar os pontos na primeira linha na camada 'paralelas_layer'
        linha = next(paralelas_layer.getFeatures(), None)
        linha_geom = linha.geometry()
        
        ponto = linha_geom.interpolate(0).asPoint()  # Início da linha
        ponto_geom = QgsGeometry.fromPointXY(QgsPointXY(ponto))

        # Inserir o primeiro ponto da linha
        ponto_feature = QgsFeature()
        ponto_feature.setFields(campos)
        ponto_feature.setAttribute("id", pontoID)
        ponto_feature.setAttribute("latitude", ponto.y())
        ponto_feature.setAttribute("longitude", ponto.x())
        ponto_feature.setGeometry(ponto_geom)
        pontos_provider.addFeature(ponto_feature)
        
        pontoID += 1
        distAtual = deltaH
        
        # Inserir os pontos restantes da linha
        while True:
            ponto = linha_geom.interpolate(distAtual).asPoint()
            ponto_geom = QgsGeometry.fromPointXY(QgsPointXY(ponto))
            
            ponto_feature = QgsFeature()
            ponto_feature.setFields(campos)
            ponto_feature.setAttribute("id", pontoID)
            ponto_feature.setAttribute("latitude", ponto.y())
            ponto_feature.setAttribute("longitude", ponto.x())
            ponto_feature.setGeometry(ponto_geom)
            pontos_provider.addFeature(ponto_feature)
            
            pontoID += 1
            distAtual += deltaH
            
            if distAtual >= comprimento:
                break

        # Atualizar a camada
        pontos_fotos.updateExtents()

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
        
        QgsProject.instance().addMapLayer(pontos_fotos)
        """
        # ==================================================================================
        # =====Obter a altitude dos pontos das Fotos========================================
        
        # OpenTopography
        
        feedback.pushInfo("Obtendo as Altitudes com o OpenTopography")
        
        # Obter as coordenadas extremas da área (em WGS 84)
        pontoN = float('-inf')  # coordenada máxima (Norte) / inf de inifito
        pontoS = float('inf')   # coordenada mínima (Sul)
        pontoW = float('inf')   # coordenada mínima (Oeste)
        pontoE = float('-inf')  # coordenada máxima (Leste)
        
        # Reprojetar Pontos (Fotos) de UTM para 4326; nesse caso EPSG:31983
        crs_wgs = QgsCoordinateReferenceSystem(4326) # WGS84 que OpenTopography usa
        
        # Transformador de coordenadas (UTM -> WGS84)
        transformador = QgsCoordinateTransform(crs, crs_wgs, QgsProject.instance())
        
        for feature in camada.getFeatures():  # Terreno
            geom = feature.geometry()
            bounds = geom.boundingBox()  # Limites da geometria em UTM

            # Transformar limites para WGS 84
            ponto_min = transformador.transform(QgsPointXY(bounds.xMinimum(), bounds.yMinimum()))
            ponto_max = transformador.transform(QgsPointXY(bounds.xMaximum(), bounds.yMaximum()))

            pontoN = max(pontoN, ponto_max.y())
            pontoS = min(pontoS, ponto_min.y())
            pontoW = min(pontoW, ponto_min.x())
            pontoE = max(pontoE, ponto_max.x())

        # Ajustar os limites
        ajuste_lat = (pontoN - pontoS) * 0.70
        ajuste_long = (pontoE - pontoW) * 0.70

        pontoN += ajuste_lat
        pontoS -= ajuste_lat
        pontoW -= ajuste_long
        pontoE += ajuste_long    

        # Obter o MDE da área
        coordenadas = f'{pontoW},{pontoE},{pontoS},{pontoN}'
        area = f"{coordenadas}[EPSG:4326]"

        result = processing.run(
                "OTDEMDownloader:OpenTopography DEM Downloader", {
                    'DEMs': 7, # 7: Copernicus Global DSM 30m
                    'Extent': area,
                    'API_key': apikey,
                    'OUTPUT': 'TEMPORARY_OUTPUT'})

        output_path = result['OUTPUT']
        camadaMDE = QgsRasterLayer(output_path, "DEM")
    
        # Valor da Altitude
        prov = pontos_fotos.dataProvider()
        pontos_fotos.startEditing()
        
        # Adicionar um campo para altitude, se não existir
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

        QgsProject.instance().addMapLayer(pontos_fotos)
        
        feedback.pushInfo("")
        feedback.pushInfo("Linha de Voo e Pontos para Fotos concluídos com sucesso!")
        
        #pontos_fotos = QgsProject.instance().mapLayersByName("Pontos Fotos")[0]
        
        # =========Exportar para o Google Earth Pro (kml)================================================
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
        
        # Verificar se o caminho KML está preenchido
        if caminho_kml and caminho_kml.endswith('.kml'):
            # Configure as opções para gravar o arquivo
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.fileEncoding = 'UTF-8'
            options.driverName = 'KML'
            options.crs = crs_wgs
            options.layerOptions = ['ALTITUDE_MODE=absolute'] 
            
            # Escrever a camada no arquivo KML
            grava = QgsVectorFileWriter.writeAsVectorFormat(pontos_reproj, caminho_kml, options)
            
            feedback.pushInfo(f"Arquivo KML exportado com sucesso para: {caminho_kml}")
        else:
            feedback.pushInfo("Caminho KML não especificado. Etapa de exportação ignorada.")
        
        if teste == True:
            QgsProject.instance().addMapLayer(pontos_reproj)
            
        # =============L I T C H I==========================================================

        # Definir novos campos xcoord e ycoord com coordenadas geográficas
        pontos_reproj.dataProvider().addAttributes([QgsField("xcoord", QVariant.Double), QgsField("ycoord", QVariant.Double)])
        pontos_reproj.updateFields()

        # Obtenha o índice dos novos campos
        idx_x = pontos_reproj.fields().indexFromName('xcoord')
        idx_y = pontos_reproj.fields().indexFromName('ycoord')

        # Inicie a edição da camada
        pontos_reproj.startEditing()

        for f in pontos_reproj.getFeatures():
            geom = f.geometry()
            if geom.isEmpty():
                continue

            point = geom.asPoint()
            x = point.x()
            y = point.y()

            f.setAttribute(idx_x, x)
            f.setAttribute(idx_y, y)

            pontos_reproj.updateFeature(f)

        pontos_reproj.commitChanges()

        # deletar campos desnecessários
        campos = ['latitude', 'longitude']
        
        pontos_reproj.startEditing()
        
        # Obtem os índices dos campos a serem deletados
        indices = [pontos_reproj.fields().indexFromName(campo) for campo in campos if campo in pontos_reproj.fields().names()]
        
        pontos_reproj.deleteAttributes(indices)
        
        pontos_reproj.commitChanges()
            
        # Mudar Sistema numérico - ponto no lugar de vírgula para separa a parte decimal - Campos Double para String
        def addCampo(camada, field_name, field_type):
            camada.dataProvider().addAttributes([QgsField(field_name, field_type)])
            camada.updateFields()
                
        pontos_reproj.startEditing()

        # Adicionar campos de texto em Pontos Reordenados
        addCampo(pontos_reproj, 'xcoord ', QVariant.String) # o espaço é para diferenciar; depois vamos deletar os campos antigos
        addCampo(pontos_reproj, 'ycoord ', QVariant.String)
        addCampo(pontos_reproj, 'alturaVoo ', QVariant.String)

        for f in pontos_reproj.getFeatures():
            x1= str(f['xcoord']).replace(',', '.')
            x2 = str(f['ycoord']).replace(',', '.')
            x3 = str(f['alturaVoo']).replace(',', '.')

            # Formatar os valores como strings com ponto como separador decimal
            x1 = "{:.6f}".format(float(x1))
            x2 = "{:.6f}".format(float(x2))
            x3 = "{:.6f}".format(float(x3))

            # Atualizar os valores dos campos de texto
            f['xcoord '] = x1
            f['ycoord '] = x2
            f['alturaVoo '] = x3

            pontos_reproj.updateFeature(f)

        pontos_reproj.commitChanges()

        # Lista de campos Double a serem removidos de Pontos Reprojetados
        camposDel = ['xcoord', 'ycoord', 'alturaVoo'] # sem o espaço
        
        pontos_reproj.startEditing()
        pontos_reproj.dataProvider().deleteAttributes([pontos_reproj.fields().indexOf(campo) for campo in camposDel if pontos_reproj.fields().indexOf(campo) != -1])
        pontos_reproj.commitChanges()

        if teste == True:
            QgsProject.instance().addMapLayer(pontos_reproj)

        # Verificar se o caminho CSV está preenchido
        if caminho_csv and caminho_csv.endswith('.csv'):
            # Exportar para o Litch (CSV já preparado)
            # Criar o arquivo CSV
            with open(caminho_csv, mode='w', newline='') as csvfile:
                # Definir os cabeçalhos do arquivo CSV
                fieldnames = [
                        "latitude", "longitude", "altitude(m)",
                        "heading(deg)", "curvesize(m)", "rotationdir",
                        "gimbalmode", "gimbalpitchangle",
                        "actiontype1", "actionparam1", "altitudemode", "speed(m/s)",
                        "poi_latitude", "poi_longitude", "poi_altitude(m)", "poi_altitudemode",
                        "photo_timeinterval", "photo_distinterval"]
                
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()

                # Ler os dados da camada Pontos
                for f in pontos_reproj.getFeatures():
                    # Extrair os valores dos campos da camada
                    x_coord = f['xcoord '] 
                    y_coord = f['ycoord ' ]

                    # Criar um dicionário de dados para cada linha do CSV
                    data = {
                        "latitude": y_coord,
                        "longitude": x_coord,
                        "altitude(m)": H, # altura do objeto
                        "heading(deg)": 360,
                        "curvesize(m)": 0,
                        "rotationdir": 0,
                        "gimbalmode": 2,
                        "gimbalpitchangle": 0,
                        "actiontype1": 1,
                        "actionparam1": 0,
                        "altitudemode": 0,
                        "speed(m/s)": 0,
                        "poi_latitude": 0,
                        "poi_longitude": 0,
                        "poi_altitude(m)": 0,
                        "poi_altitudemode": 0,
                        "photo_timeinterval": -1,
                        "photo_distinterval": deltaH}

                    # Escrever a linha no CSV
                    writer.writerow(data)
        else:
            feedback.pushInfo("Caminho CSV não especificado. Etapa de exportação ignorada.")

        # Mensagem de Encerramento
        feedback.pushInfo("")
        feedback.pushInfo("Plano de Voo Vertical executado com sucesso.") 
        """    
        return {}
        
    def name(self):
        return 'PlanoVooV'.lower()

    def displayName(self):
        return self.tr('Pontos Fotos - Voo Vertical')

    def group(self):
        return self.tr(self.groupId())

    def groupId(self):
        return ''
        
    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return PlanoVoo_V()
    
    def icon(self):
        return QIcon(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'images/PlanoVoo.png'))
    
    texto = "Este algoritmo calcula a 'Linha do Voo' e uma camada dos 'Pontos' para Fotos. \
            Gera ainda: a planilha CSV para importar no Litchi e o arquivo KML para Google Earth. \
            Se você usa um aplicativo para Voo que não seja o Litchi, pode usar os pontos gerados no QGIS."
    figura = 'images/PlanoVoo2.jpg'

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
  