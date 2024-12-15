# -*- coding: utf-8 -*-

"""
/***************************************************************************
 PlanoVoo - Funções
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
__date__ = '2024-12-02'
__copyright__ = '(C) 2024 by Prof Cazaroli e Leandro França'
__revision__ = '$Format:%H$'

from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProcessingFeedback, QgsFeature, QgsProperty, QgsWkbTypes, QgsTextBufferSettings
from qgis.core import QgsProject, QgsVectorLayer, QgsRasterLayer, QgsField, QgsPointXY, QgsVectorFileWriter, QgsPalLayerSettings, QgsTextFormat, QgsVectorLayerSimpleLabeling
from qgis.core import QgsMarkerSymbol, QgsSingleSymbolRenderer, QgsSimpleLineSymbolLayer, QgsLineSymbol, QgsMarkerLineSymbolLayer, QgsFillSymbol
from qgis.PyQt.QtGui import QColor, QFont
from PyQt5.QtCore import QVariant
import processing
import csv

def obter_DEM(tipo_voo, geometria, transformador, apikey, feedback=None, bbox_area_min=2.5):
   # Obter a Altitude dos pontos das Fotos com OpenTopography
   feedback.pushInfo("Obtendo as Altitudes com o OpenTopography")
   
   # Obter as coordenadas extremas da área (em WGS 84)
   pontoN = float('-inf')  # coordenada máxima (Norte) / inf de inifito
   pontoS = float('inf')   # coordenada mínima (Sul)
   pontoW = float('inf')   # coordenada mínima (Oeste)
   pontoE = float('-inf')  # coordenada máxima (Leste)
   
   # Determinar o bounding box da linha em WGS 84
   if tipo_voo == "H":
      for feature in geometria.getFeatures():  # Terreno
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
   else: # VF e VC
      bounds = geometria.boundingBox()
      ponto_min = transformador.transform(QgsPointXY(bounds.xMinimum(), bounds.yMinimum()))
      ponto_max = transformador.transform(QgsPointXY(bounds.xMaximum(), bounds.yMaximum()))

      pontoN = ponto_max.y()
      pontoS = ponto_min.y()
      pontoW = ponto_min.x()
      pontoE = ponto_max.x()

      # Certificar que a área do bounding box seja grande o suficiente
      bbox_area = (pontoE - pontoW) * (pontoN - pontoS) * 111 * 111  # Aproximação em km²
      if bbox_area < bbox_area_min:
         aumento = ((bbox_area_min / bbox_area) ** 0.5 - 1) / 2
         ajuste_lat_extra = aumento * (pontoN - pontoS)
         ajuste_long_extra = aumento * (pontoE - pontoW)
         pontoN += ajuste_lat_extra
         pontoS -= ajuste_lat_extra
         pontoW -= ajuste_long_extra
         pontoE += ajuste_long_extra

   # Obter o DEM da área
   coordenadas = f'{pontoW},{pontoE},{pontoS},{pontoN}'
   area = f"{coordenadas}[EPSG:4326]"

   result = processing.run(
      "OTDEMDownloader:OpenTopography DEM Downloader", {
         'DEMs': 7,  # Copernicus Global DSM 30m
         'Extent': area,
         'API_key': apikey,
         'OUTPUT': 'TEMPORARY_OUTPUT'
      })

   output_path = result['OUTPUT']
   camadaMDE = QgsRasterLayer(output_path, "DEM")

   # Filtrar o MDE com (Relevo / Filtro do MDE) do LFTools
   result = processing.run(
      "lftools:demfilter", {
         'INPUT': camadaMDE,
         'KERNEL': 0,
         'OUTPUT': 'TEMPORARY_OUTPUT',
         'OPEN': False
      })
   output_path = result['OUTPUT']
   camadaMDE = QgsRasterLayer(output_path, "DEM")

   feedback.pushInfo("DEM processado com sucesso!")
   
   return camadaMDE
 
def gerar_KML(camada, arquivo_kml, nome, crs_wgs, feedback=None):
   # Configuração das opções para gravar o arquivo
   options = QgsVectorFileWriter.SaveVectorOptions()
   options.fileEncoding = 'UTF-8'
   options.driverName = 'KML'
   options.field_name = 'id'
   options.crs = crs_wgs
   options.layerName = nome
   options.layerOptions = ['ALTITUDE_MODE=absolute']

   # Escrever a camada no arquivo KML
   grava = QgsVectorFileWriter.writeAsVectorFormat(camada, arquivo_kml, options)

   if grava == QgsVectorFileWriter.NoError:
      feedback.pushInfo(f"Arquivo KML exportado com sucesso para: {arquivo_kml}")
   else:
      feedback.pushInfo(f"Erro ao exportar o arquivo KML: {grava}")
      
   return {}

def gerar_CSV(tipo_voo, pontos_reproj, arquivo_csv, velocidade, delta, angulo, H):
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

         ponto = geom.asPoint()
         x = ponto.x()
         y = ponto.y()

         f.setAttribute(idx_x, x)
         f.setAttribute(idx_y, y)

         pontos_reproj.updateFeature(f)

   pontos_reproj.commitChanges()

   # deletar campos desnecessários
   if tipo_voo == "H" or tipo_voo == "VC":
      campos = ['latitude', 'longitude']
   elif tipo_voo == "VF":
      campos = ['linha', 'latitude', 'longitude']
   
   pontos_reproj.startEditing()
   
   # Obtem os índices dos campos a serem deletados
   indices = [pontos_reproj.fields().indexFromName(campo) for campo in campos if campo in pontos_reproj.fields().names()]
   
   pontos_reproj.deleteAttributes(indices)
   
   pontos_reproj.commitChanges()
         
   # Mudar Sistema numérico - ponto no lugar de vírgula para separa a parte decimal - Campos Double para String        
   pontos_reproj.startEditing()

   # Adicionar campos de texto em Pontos Reordenados
   addCampo(pontos_reproj, 'xcoord ', QVariant.String) # o espaço é para diferenciar; depois vamos deletar os campos antigos
   addCampo(pontos_reproj, 'ycoord ', QVariant.String)
   addCampo(pontos_reproj, 'alturavoo ', QVariant.String)
      
   if tipo_voo == "VC":
      addCampo(pontos_reproj, 'angulo ', QVariant.String)   
   
   for f in pontos_reproj.getFeatures():
         x1= str(f['xcoord']).replace(',', '.')
         x2 = str(f['ycoord']).replace(',', '.')
         x3 = str(f['alturavoo']).replace(',', '.')
         
         if tipo_voo == "VC":
            x4 = str(f['angulo']).replace(',', '.')
         
         # Formatar os valores como strings com ponto como separador decimal
         x1 = "{:.6f}".format(float(x1))
         x2 = "{:.6f}".format(float(x2))
         x3 = "{:.6f}".format(float(x3))

         if tipo_voo == "VC":
            x4 = "{:.6f}".format(float(x4))

         # Atualizar os valores dos campos de texto
         f['xcoord '] = x1
         f['ycoord '] = x2
         f['alturavoo '] = x3
         
         if tipo_voo == "VC":
            f['angulo '] = x4

         pontos_reproj.updateFeature(f)

   pontos_reproj.commitChanges()

   # Lista de campos Double a serem removidos de Pontos Reprojetados
   if tipo_voo == "H" or tipo_voo == "VF":
      camposDel = ['xcoord', 'ycoord', 'alturaVoo'] # sem o espaço
   elif tipo_voo == "VC":
      camposDel = ['xcoord', 'ycoord', 'alturavoo', 'angulo']
      
   pontos_reproj.startEditing()
   pontos_reproj.dataProvider().deleteAttributes([pontos_reproj.fields().indexOf(campo) for campo in camposDel if pontos_reproj.fields().indexOf(campo) != -1])
   pontos_reproj.commitChanges()
   
   # Formatar os valores como strings com ponto como separador decimal
   v = str(velocidade).replace(',', '.')
   velocidade = "{:.6f}".format(float(v))
   
   # Exportar para o Litch (CSV já preparado)
   # Criar o arquivo CSV
   with open(arquivo_csv, mode='w', newline='') as csvfile:
         # Definir os cabeçalhos do arquivo CSV
         fieldnames = [
               "latitude", "longitude", "altitude(m)",
               "heading(deg)", "curvesize(m)", "rotationdir",
               "gimbalmode", "gimbalpitchangle",
               "actiontype1", "actionparam1", "actiontype2", "actionparam2",
               "actiontype3", "actionparam3", "actiontype4", "actionparam4",
               "actiontype5", "actionparam5", "actiontype6", "actionparam6",
               "actiontype7", "actionparam7", "actiontype8", "actionparam8",
               "actiontype9", "actionparam9", "actiontype10", "actionparam10",
               "actiontype11", "actionparam11", "actiontype12", "actionparam12",
               "actiontype13", "actionparam13", "actiontype14", "actionparam14",
               "actiontype15", "actionparam15", "altitudemode", "speed(m/s)",
               "poi_latitude", "poi_longitude", "poi_altitude(m)", "poi_altitudemode",
               "photo_timeinterval", "photo_distinterval"]
         
         writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
         writer.writeheader()
         
         if tipo_voo == "H":
            alturavoo = H
            gimbal = 0
            angulo_gimbal = -90
            above_ground = 1 # Above Ground habilitado
         else:
            gimbal = 2
            angulo_gimbal = 0
            above_ground = 0 # Above Ground não habilitado

         # Ler os dados da camada Pontos
         for f in pontos_reproj.getFeatures():
            # Extrair os valores dos campos da camada
            x_coord = f['xcoord '] 
            y_coord = f['ycoord ']
            
            if tipo_voo == "VF":
               alturavoo = f['alturavoo ']
            elif tipo_voo == "VC":
               alturavoo = f['alturavoo ']
               angulo = f['angulo ']
               
            # Criar um dicionário de dados para cada item do CSV
            data = {
               "latitude": y_coord,
               "longitude": x_coord,
               "altitude(m)": alturavoo,
               "heading(deg)": angulo,
               "curvesize(m)": 0,
               "rotationdir": 0,
               "gimbalmode": gimbal,
               "gimbalpitchangle": angulo_gimbal,
               "actiontype1": 0,     # STAY 2 segundos
               "actionparam1": 2000,
               "actiontype2": 1,     # TAKE_PHOTO
               "actionparam2": 0,
               "actiontype3": -1, 
               "actionparam3": 0,
               "actiontype4": -1,
               "actionparam4": 0,
               "actiontype5": -1,
               "actionparam5": 0,
               "actiontype6": -1,
               "actionparam6": 0,
               "actiontype7": -1,
               "actionparam7": 0,
               "actiontype8": -1,
               "actionparam8": 0,
               "actiontype9": -1,
               "actionparam9": 0,
               "actiontype10": -1,
               "actionparam10": 0,
               "actiontype11": -1,
               "actionparam11": 0,
               "actiontype12": -1,
               "actionparam12": 0,
               "actiontype13": -1,
               "actionparam13": 0,
               "actiontype14": -1,
               "actionparam14": 0,
               "actiontype15": -1,
               "actionparam15": 0,
               "altitudemode": above_ground,
               "speed(m/s)": velocidade,
               "poi_latitude": 0,
               "poi_longitude": 0,
               "poi_altitude(m)": 0,
               "poi_altitudemode": 0,
               "photo_timeinterval": -1,
               "photo_distinterval": delta}

            # Escrever a linha no CSV
            writer.writerow(data)
            
   return {}

def addCampo(camada, field_name, field_type):
      camada.dataProvider().addAttributes([QgsField(field_name, field_type)])
      camada.updateFields()
      
def set_Z_value(camada, z_field):
    result = processing.run("native:setzvalue", {
        'INPUT': camada,
        'Z_VALUE': QgsProperty.fromExpression(f'"{z_field}"'),
        'OUTPUT': 'TEMPORARY_OUTPUT'
    })
    
    output_layer = result['OUTPUT']
    output_layer.setName(camada.name())
    
    return output_layer
 
def reprojeta_camada_WGS84(camada, crs_wgs, transformador):
   geometry_type = camada.geometryType()
   
   # Criar camada reprojetada com base no tipo de geometria
   if geometry_type == QgsWkbTypes.PointGeometry:
      tipo_geometria = "Point"
   elif geometry_type == QgsWkbTypes.LineGeometry:
      tipo_geometria = "LineString"
   elif geometry_type == QgsWkbTypes.PolygonGeometry:
      tipo_geometria = "Polygon"
   
   # Criar a nova camada reprojetada em memória
   camada_reproj = QgsVectorLayer(f"{tipo_geometria}?crs={crs_wgs.authid()}", f"{camada.name()}_Reprojetada", "memory")
    
   camada_reproj.startEditing()
   camada_reproj.dataProvider().addAttributes(camada.fields())
   camada_reproj.updateFields()

   # Reprojetar feições
   for f in camada.getFeatures():
      geom = f.geometry()
      geom.transform(transformador)
      reproj = QgsFeature()
      reproj.setGeometry(geom)
      reproj.setAttributes(f.attributes())
      camada_reproj.addFeature(reproj)

   camada_reproj.commitChanges()
   
   return camada_reproj

def simbologiaLinhaVoo(tipo_voo, camada):
   if tipo_voo == "H":
      line_symbol = QgsLineSymbol.createSimple({'color': 'blue', 'width': '0.3'})  # Linha base

      seta = QgsMarkerSymbol.createSimple({'name': 'arrow', 'size': '5', 'color': 'blue', 'angle': '90'})

      marcador = QgsMarkerLineSymbolLayer()
      marcador.setInterval(30)  # Define o intervalo entre as setas (marcadores)
      marcador.setSubSymbol(seta)
      
      camada.renderer().symbol().appendSymbolLayer(marcador)
   elif tipo_voo == "VC" or tipo_voo == "VF":
      simbologia = QgsFillSymbol.createSimple({
            'color': 'transparent',    # Sem preenchimento
            'outline_color': 'green',  # Contorno verde
            'outline_width': '0.8'     # Largura do contorno
        })
      
      camada.setRenderer(QgsSingleSymbolRenderer(simbologia))
        
   return

def simbologiaPontos(camada):
   simbolo = QgsMarkerSymbol.createSimple({'color': 'blue', 'size': '3'})
   renderer = QgsSingleSymbolRenderer(simbolo)
   camada.setRenderer(renderer)

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

   camada.setLabelsEnabled(True)
   camada.setLabeling(QgsVectorLayerSimpleLabeling(settings))

   camada.triggerRepaint()
   
   return