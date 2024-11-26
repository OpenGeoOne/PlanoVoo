

from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from .resources import *
from .PlanoVoo_dialog import PlanoVooDialog
import os.path
import processing
from qgis.core import (
    QgsProject, QgsRasterLayer, QgsVectorLayer, QgsFeature, QgsField, QgsFields, 
    QgsGeometry, QgsPoint, QgsPointXY, QgsRaster, QgsWkbTypes, edit, QgsCoordinateReferenceSystem,
    QgsVectorFileWriter, QgsCoordinateTransform
)
from PyQt5.QtCore import QVariant
import csv


    projeto = QgsProject.instance()

    # ==================================================================================
    # ===OpenTopography=================================================================
    
    # Obter as coordenadas extremas da área
    camada = self.dlg.cmbArea.currentText()
    camada = projeto.mapLayersByName(camada)[0]

    pontoN = float('-inf')  # coordenada máxima (Norte) / inf de inifito
    pontoS = float('inf')   # coordenada mínima (Sul)
    pontoW = float('inf')   # coordenada mínima (Oeste)
    pontoE = float('-inf')  # coordenada máxima (Leste)
    
    for feature in camada.getFeatures():
        geom = feature.geometry()
        bounds = geom.boundingBox() # Obtém os limites da geometria

        pontoN = max(pontoN, bounds.yMaximum())
        pontoS = min(pontoS, bounds.yMinimum())
        pontoW = min(pontoW, bounds.xMinimum())
        pontoE = max(pontoE, bounds.xMaximum())

    ajuste_lat = (pontoN - pontoS) * 0.70
    ajuste_long = (pontoE - pontoW) * 0.70
    
    pontoN += ajuste_lat
    pontoS -= ajuste_lat
    pontoW -= ajuste_long
    pontoE += ajuste_long    

    # obter o MDE da área
    src = projeto.crs()              # [EPSG:<QgsCoordinateReferenceSystem: EPSG:31983>]
    src = src.authid().split(":")[1] # 31983
    coordenadas = f'{pontoW},{pontoE},{pontoS},{pontoN}'
    area = f"{coordenadas}[EPSG:{src}]"
    apiKey = 'd0fd2bf40aa8a6225e8cb6a4a1a5faf7'

    result = processing.run(
            "OTDEMDownloader:OpenTopography DEM Downloader", {
                'DEMs': 7,
                'Extent': area,
                'API_key': apiKey,
                'OUTPUT': 'TEMPORARY_OUTPUT'})

    output_path = result['OUTPUT']
    camadaMDE = QgsRasterLayer(output_path, "DEM")

    # ==================================================================================
    # === Reprojetar Camada Pontos (Fotos) de 31983 para 4326===========================
    camada = self.dlg.cmbFotos.currentText()
    camada = projeto.mapLayersByName(camada)[0] # Camada Pontos (Fotos)

    src = camada.crs() # EPSG:31983
    srcDestino = QgsCoordinateReferenceSystem(4326) # EPSG:4326

    # Configuração do transformador
    transform_context = QgsProject.instance().transformContext()
    transform = QgsCoordinateTransform(src, srcDestino, transform_context)

    # Crie uma nova camada para os dados reprojetados
    camadaReproj = QgsVectorLayer("Point?crs=EPSG:4326", "Pontos_reprojetados", "memory")
    camadaReproj.startEditing()
    camadaReproj.dataProvider().addAttributes(camada.fields())
    camadaReproj.updateFields()

    # Reprojetar os pontos
    for f in camada.getFeatures():
        geom = f.geometry()
        geom.transform(transform)
        reprojFeature = QgsFeature()
        reprojFeature.setGeometry(geom)
        reprojFeature.setAttributes(f.attributes())
        camadaReproj.addFeature(reprojFeature)

    camadaReproj.commitChanges()
    
    # ==================================================================================
    # ====Obter Cota Z - Pontos e DEM ==================================================
    alturaVoo = self.dlg.spbAlturaVoo.value() # altura de Voo

    # Adicionar o campo "Z" na camada de pontos se ainda não existir
    if camadaReproj.fields().indexFromName('Z') == -1:
        camadaReproj.dataProvider().addAttributes([QgsField('Z', QVariant.Double)])
        camadaReproj.updateFields()

    camada.startEditing()

    # definir o valor de Z
    for f in camadaReproj.getFeatures():
        point = f.geometry().asPoint()
        x, y = point.x(), point.y()
        
        # Obter o valor de Z do MDE
        mde = camadaMDE.dataProvider().identify(QgsPointXY(x, y), QgsRaster.IdentifyFormatValue)
        z_value = mde.results()[1]  # O valor de Z está no índice 1
        
        # Atualizar o campo "Z" da feature
        f['Z'] = z_value + alturaVoo
        camadaReproj.updateFeature(f)

    camadaReproj.commitChanges()
    
    # ==================================================================================
    # ===Exportar para o Google Earth Pro (kml)========================================
    camArq = self.dlg.arqKml.filePath()
    
    # Configure as opções para o escritor de arquivos
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.fileEncoding = 'UTF-8'
    options.driverName = 'KML'
    options.crs = QgsCoordinateReferenceSystem('EPSG:4326')
    options.layerOptions = ['ALTITUDE_MODE=absolute'] 

    # Crie o escritor de arquivos
    writer = QgsVectorFileWriter.writeAsVectorFormat(camadaReproj, camArq, options)
    
    # =============L I T C H I==========================================================
    # ====Colocar a cota Z em alturaVoo(altura do Voo)==================================
    camadaReproj.startEditing()

    for f in camadaReproj.getFeatures():
        f['Z'] = alturaVoo
        camadaReproj.updateFeature(f)

    camadaReproj.commitChanges()
    
    # ==================================================================================
    # ===Definir Atributos de Geometria=================================================
    camadaReproj.dataProvider().addAttributes([QgsField("xcoord", QVariant.Double),
                                                    QgsField("ycoord", QVariant.Double)])
    camadaReproj.updateFields()

    # Obtenha o índice dos novos campos
    idx_x = camadaReproj.fields().indexFromName('xcoord')
    idx_y = camadaReproj.fields().indexFromName('ycoord')

    # Inicie a edição da camada
    camadaReproj.startEditing()

    for f in camadaReproj.getFeatures():
        geom = f.geometry()
        if geom.isEmpty():
            continue

        point = geom.asPoint()
        x = point.x()
        y = point.y()

        f.setAttribute(idx_x, x)
        f.setAttribute(idx_y, y)

        camadaReproj.updateFeature(f)

    camadaReproj.commitChanges()
    
    # ==================================================================================
    # ===Mapeamento dos campos antigos para os novos nomes==============================
    campos = camadaReproj.fields()
            
    novos_nomes = {
        'id': 'Waypoint Number',
        'latitude': 'Y [m]',
        'longitude': 'X [m]',
        'Z': 'Alt. ASL [m]',
        'xcoord': 'xcoord',
        'ycoord': 'ycoord'}

    # Adicionar novos campos à camada
    novoCampos = QgsFields()
    for f in campos:
        novoNome = novos_nomes.get(f.name(), f.name())
        novoCampo = QgsField(novoNome, f.type())
        novoCampos.append(novoCampo)

    # Criar uma nova camada com os campos renomeados
    camadaRenomeados = QgsVectorLayer(f'Point?crs={camada.crs().authid()}', 'Pontos_renomeados', 'memory')
    provider = camadaRenomeados.dataProvider()
    provider.addAttributes(novoCampos)
    camadaRenomeados.updateFields()

    # Copiar os recursos da camada original para a nova camada
    with edit(camadaRenomeados):
        for f in camadaReproj.getFeatures():
            novaFeature = QgsFeature(camadaRenomeados.fields())
            novaFeature.setGeometry(f.geometry())
            
            novaFeature.setAttributes(f.attributes())
            camadaRenomeados.dataProvider().addFeature(novaFeature)

    # ==================================================================================
    # ===Adicionar o novo campo 'Alt. AGL [m]'==========================================
    campos = camadaRenomeados.fields()

    novoCampo = QgsField('Alt. AGL [m]', QVariant.Double) # QVariant.Double p/valores numéricos
    camadaRenomeados.dataProvider().addAttributes([novoCampo])
    camadaRenomeados.updateFields()
    
    # ==================================================================================
    # ====Trocar Coluna X e Y de lugar e columa Alt. AGL [m]============================

    # Definindo a nova ordem dos campos
    novaOrdem = ['Waypoint Number', 'X [m]', 'Y [m]', 'Alt. ASL [m]', 'Alt. AGL [m]', 'xcoord', 'ycoord']

    # Criando uma nova camada de memória com a nova ordem de campos
    camadaReordenados = QgsVectorLayer(f'Point?crs={camadaRenomeados.crs().authid()}', 'Pontos_reordenados', 'memory')
    provider = camadaReordenados.dataProvider()

    # Adicionando os campos na nova ordem
    novosCampos = QgsFields()
    for field_name in novaOrdem:
        field = camadaRenomeados.fields().field(field_name)
        novosCampos.append(field)
        
    provider.addAttributes(novosCampos)
    camadaReordenados.updateFields()

    # Copiando os registros da camada original para a nova camada
    for f in camadaRenomeados.getFeatures():
        n = QgsFeature(camadaReordenados.fields())
        n.setGeometry(f.geometry())
        
        for field_name in novaOrdem:
            n.setAttribute(field_name, f[field_name])
        
        provider.addFeature(n)

    # ==================================================================================
    # ====Multiplicar por -1 as latitudes e longitudes==================================
    camadaReordenados.startEditing()

    for f in camadaReordenados.getFeatures():
        xcoord = f['xcoord']
        x = f['X [m]']
        
        ycoord = f['ycoord']
        y = f['Y [m]']
        
        # Se 'xcoord' for negativo, multiplica 'X [m]' por -1
        if xcoord < 0:
            x = x * -1
            
            f.setAttribute(f.fieldNameIndex('X [m]'), x)
            camadaReordenados.updateFeature(f)
            
        if ycoord < 0:
            y = y * -1
            
            f.setAttribute(f.fieldNameIndex('Y [m]'), y)
            camadaReordenados.updateFeature(f)

    camadaReordenados.commitChanges()
    
    # ==================================================================================
    # ====Renumerar a coluna de IDs - Waypoint Number==================================
    camadaReordenados.startEditing()
        
    n = 1

    for f in camadaReordenados.getFeatures():
        f['Waypoint Number'] = n
        camadaReordenados.updateFeature(f)
        n += 1

    camadaReordenados.commitChanges()
    
    # ==================================================================================
    # ====Mudar Sistema numérico - ponto no lugar de vírgula para separa a parte decimal
    def addCampo(camada, field_name, field_type):
        camada.dataProvider().addAttributes([QgsField(field_name, field_type)])
        camada.updateFields()

    def delCampo(camada, campo):
        camada.dataProvider().deleteAttributes([camada.fields().indexOf(campo)])
        camada.updateFields()
            
    camadaReordenados.startEditing()

    # Adicionar campos de texto
    addCampo(camadaReordenados, 'X [m] ', QVariant.String) # observe o espaço em branco no
    addCampo(camadaReordenados, 'Y [m] ', QVariant.String) # final para diferenciar
    addCampo(camadaReordenados, 'Alt. ASL [m] ', QVariant.String)
    addCampo(camadaReordenados, 'Alt. AGL [m] ', QVariant.String)
    addCampo(camadaReordenados, 'xcoord ', QVariant.String)
    addCampo(camadaReordenados, 'ycoord ', QVariant.String)

    for f in camadaReordenados.getFeatures():
        x1 = str(f['X [m]']).replace(',', '.')
        x2 = str(f['Y [m]']).replace(',', '.')
        x3 = str(f['Alt. ASL [m]']).replace(',', '.')
        x4 = 'nan'
        x5 = str(f['xcoord']).replace(',', '.')
        x6 = str(f['ycoord']).replace(',', '.')

        # Formatar os valores como strings com ponto como separador decimal
        x1 = "{:.6f}".format(float(x1))
        x2 = "{:.6f}".format(float(x2))
        x3 = "{:.6f}".format(float(x3))
        
        x5 = "{:.6f}".format(float(x5))
        x6 = "{:.6f}".format(float(x6))

        # Atualizar os valores dos campos de texto
        f['X [m] '] = x1
        f['Y [m] '] = x2
        f['Alt. ASL [m] '] = x3
        f['Alt. AGL [m] '] = x4
        f['xcoord '] = x5
        f['ycoord '] = x6

        camadaReordenados.updateFeature(f)

    camadaReordenados.commitChanges()

    camadaReordenados.startEditing()

    # Lista de campos Double a serem removidos
    camposDel = ['X [m]', 'Y [m]', 'Alt. ASL [m]', 'Alt. AGL [m]', 'xcoord', 'ycoord'] # sem o espaço
    for f in camposDel:
        delCampo(camadaReordenados, f)

    camadaReordenados.commitChanges()
    
    # ==================================================================================
    # ====Exportar para o Litich (csv preparado)========================================
    camArq = self.dlg.arqCSV.filePath()
    
    espacFrontal = 35 # vc coloca o valor do espaçamento frontal da 1a. parte do Plugin (Curso 3)

    # Criar o arquivo CSV
    with open(camArq, mode='w', newline='') as csvfile:
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
        
        # Criar o escritor CSV
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        # Ler os dados da camada Pontos
        for f in camadaReordenados.getFeatures():
            # Extrair os valores dos campos da camada
            x_coord = f['xcoord '] # atenção ao espaço
            y_coord = f['ycoord ' ]
            altitude = f['Alt. ASL [m] ']

            # Criar um dicionário de dados para cada linha do CSV
            data = {
                "latitude": y_coord,
                "longitude": x_coord,
                "altitude(m)": altitude,
                "heading(deg)": 360,
                "curvesize(m)": 0,
                "rotationdir": 0,
                "gimbalmode": 0,
                "gimbalpitchangle": -90,
                "actiontype1": -1,
                "actionparam1": 0,
                "actiontype2": -1,
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
                "altitudemode": 1,
                "speed(m/s)": 0,
                "poi_latitude": 0,
                "poi_longitude": 0,
                "poi_altitude(m)": 0,
                "poi_altitudemode": 0,
                "photo_timeinterval": -1,
                "photo_distinterval": espacFrontal}

            # Escrever a linha no CSV
            writer.writerow(data)
    
    # ==================================================================================
    # ====Mensagem de Encerramento======================================================
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Information)
    msg.setWindowTitle("Plugin Plano de Voo") 
    msg.setText("Plugin executado com sucesso.")
    msg.setStandardButtons(QMessageBox.Ok)
    msg.exec_()

