from __future__ import print_function
import logging
import numpy
import os
import unittest
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from DICOMLib import DICOMUtils

#
# DICOMReaders
#

class DICOMReaders(ScriptedLoadableModule):
  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    parent.title = "DICOMReaders"
    parent.categories = ["DICOMReaders"]
    parent.dependencies = []
    parent.contributors = ["Steve Pieper (Isomics)"]
    parent.helpText = """
    This module was developed to confirm that different DICOM reading approaches result in the same volumes loaded in Slicer (or that old readers fail but fixed readers succeed).
    """
    parent.acknowledgementText = """This work is supported primarily by the National Institutes of Health, National Cancer Institute, Informatics Technology for Cancer Research (ITCR) program, grant Quantitative Image Informatics for Cancer Research (QIICR) (U24 CA180918, PIs Kikinis and Fedorov). We also acknowledge support of the following grants: Neuroimage Analysis Center (NAC) (P41 EB015902, PI Kikinis) and National Center for Image Guided Therapy (NCIGT) (P41 EB015898, PI Tempany).
    This file was originally developed by Steve Pieper, Isomics, Inc.
""" # replace with organization, grant and thanks.

#
# qDICOMReadersWidget
#

class DICOMReadersWidget(ScriptedLoadableModuleWidget):

  def setup(self):
    # Instantiate and connect widgets ...
    ScriptedLoadableModuleWidget.setup(self)

    self.layout.addStretch(1)


class DICOMReadersTest(ScriptedLoadableModuleTest):
  """
  This is the test case
  """

  def setUp(self):
    """ Do whatever is needed to reset the state - typically a scene clear will be enough.
    """
    self.delayDisplay("Closing the scene")
    layoutManager = slicer.app.layoutManager()
    layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutConventionalView)
    slicer.mrmlScene.Clear(0)

  def runTest(self):
    """Run as few or as many tests as needed here.
    """
    self.setUp()
    self.test_AlternateReaders()
    self.setUp()
    self.test_MissingSlices()

  def test_AlternateReaders(self):
    """ Test the DICOM loading of sample testing data
    """
    testPass = True
    import os, json
    self.delayDisplay("Starting the DICOM test")

    referenceData = [
      { "url": "http://slicer.kitware.com/midas3/download?items=292839",
        "fileName": "Mouse-MR-example-where-GDCM_fails.zip",
        "name": "Mouse-MR-example-where-GDCM_fails",
        "seriesUID": "1.3.6.1.4.1.9590.100.1.2.366426457713813178933224342280246227461",
        "expectedFailures": ["GDCM", "Archetype"],
        "voxelValueQuantity": "(110852, DCM, \"MR signal intensity\")",
        "voxelValueUnits": "(1, UCUM, \"no units\")"
      },
      { "url": "http://slicer.kitware.com/midas3/download?items=294857",
        "fileName": "deidentifiedMRHead-dcm-one-series.zip",
        "name": "deidentifiedMRHead-dcm-one-series",
        "seriesUID": "1.3.6.1.4.1.5962.99.1.3814087073.479799962.1489872804257.270.0",
        "expectedFailures": [],
        "voxelValueQuantity": "(110852, DCM, \"MR signal intensity\")",
        "voxelValueUnits": "(1, UCUM, \"no units\")"
      }
    ]

    # another dataset that could be added in the future - currently fails for all readers
    # due to invalid format - see https://issues.slicer.org/view.php?id=3569
      #{ "url": "http://slicer.kitware.com/midas3/download/item/293587/RIDER_bug.zip",
        #"fileName": "RIDER_bug.zip",
        #"name": "RIDER_bug",
        #"seriesUID": "1.3.6.1.4.1.9328.50.7.261772317324041365541450388603508531852",
        #"expectedFailures": []
      #}

    loadingResult = {}
    #
    # first, get the data - a zip file of dicom data
    #
    self.delayDisplay("Downloading")
    for dataset in referenceData:
      try:
        import SampleData
        dicomFilesDirectory = SampleData.downloadFromURL(
          fileNames=dataset['fileName'], uris=dataset['url'])[0]
        self.delayDisplay('Finished with download')

        #
        # insert the data into th database
        #
        self.delayDisplay("Switching to temp database directory")
        originalDatabaseDirectory = DICOMUtils.openTemporaryDatabase('tempDICOMDatabase')

        self.delayDisplay('Importing DICOM')
        mainWindow = slicer.util.mainWindow()
        mainWindow.moduleSelector().selectModule('DICOM')

        indexer = ctk.ctkDICOMIndexer()
        indexer.addDirectory(slicer.dicomDatabase, dicomFilesDirectory, None)
        indexer.waitForImportFinished()

        #
        # select the series
        #
        detailsPopup = slicer.modules.DICOMWidget.detailsPopup
        detailsPopup.open()
        # load the data by series UID
        detailsPopup.offerLoadables(dataset['seriesUID'],'Series')
        detailsPopup.examineForLoading()
        loadable = list(detailsPopup.getAllSelectedLoadables().keys())[0]

        #
        # try loading using each of the selected readers, fail
        # on enexpected load issue
        #
        scalarVolumePlugin = slicer.modules.dicomPlugins['DICOMScalarVolumePlugin']()
        readerApproaches = scalarVolumePlugin.readerApproaches()
        basename = loadable.name
        volumesByApproach = {}
        for readerApproach in readerApproaches:
          self.delayDisplay('Loading Selection with approach: %s' % readerApproach)
          loadable.name = basename + "-" + readerApproach
          volumeNode = scalarVolumePlugin.load(loadable,readerApproach)
          if not volumeNode and readerApproach not in dataset['expectedFailures']:
            raise Exception("Expected to be able to read with %s, but couldn't" % readerApproach)
          if volumeNode and readerApproach in dataset['expectedFailures']:
            raise Exception("Expected to NOT be able to read with %s, but could!" % readerApproach)
          if volumeNode:
            volumesByApproach[readerApproach] = volumeNode

            self.delayDisplay('Test quantity and unit')
            if 'voxelValueQuantity' in dataset.keys():
              self.assertEqual(volumeNode.GetVoxelValueQuantity().GetAsPrintableString(), dataset['voxelValueQuantity'])
            if 'voxelValueUnits' in dataset.keys():
              self.assertEqual(volumeNode.GetVoxelValueUnits().GetAsPrintableString(), dataset['voxelValueUnits'])


        #
        # for each approach that loaded as expected, compare the volumes
        # to ensure they match in terms of pixel data and metadata
        #
        failedComparisons = {}
        approachesThatLoaded = list(volumesByApproach.keys())
        print('approachesThatLoaded %s' % approachesThatLoaded)
        for approachIndex in range(len(approachesThatLoaded)):
          firstApproach = approachesThatLoaded[approachIndex]
          firstVolume = volumesByApproach[firstApproach]
          for secondApproachIndex in range(approachIndex+1,len(approachesThatLoaded)):
            secondApproach = approachesThatLoaded[secondApproachIndex]
            secondVolume = volumesByApproach[secondApproach]
            print('comparing  %s,%s' % (firstApproach, secondApproach))
            comparison = slicer.modules.dicomPlugins['DICOMScalarVolumePlugin'].compareVolumeNodes(firstVolume,secondVolume)
            if comparison != "":
              print(('failed: %s', comparison))
              failedComparisons[firstApproach,secondApproach] = comparison

        if len(failedComparisons.keys()) > 0:
          raise Exception("Loaded volumes don't match: %s" % failedComparisons)

        self.delayDisplay('%s Test passed!' % dataset['name'])

      except Exception as e:
        import traceback
        traceback.print_exc()
        self.delayDisplay('%s Test caused exception!\n' % dataset['name'] + str(e))
        testPass = False

    self.delayDisplay("Restoring original database directory")
    mainWindow.moduleSelector().selectModule('DICOMReaders')

    logging.info(loadingResult)

    return testPass

  def test_MissingSlices(self):
    """ Test behavior of the readers when slices are missing

    To edit and run this test from the python console, paste this below:

reloadScriptedModule('DICOMReaders'); import DICOMReaders; tester = DICOMReaders.DICOMReadersTest(); tester.setUp(); tester.test_MissingSlices()

    """
    testPass = True
    import os, json
    self.delayDisplay("Starting the DICOM test")

    import SampleData
    dicomFilesDirectory = SampleData.downloadFromURL(
      fileNames='deidentifiedMRHead-dcm-one-series.zip',
      uris='http://slicer.kitware.com/midas3/download?items=294857')[0]
    self.delayDisplay('Finished with download\n')

    seriesUID = "1.3.6.1.4.1.5962.99.1.3814087073.479799962.1489872804257.270.0"
    seriesRASBounds = [-87.29489517211913, 81.70450973510744,
                       -121.57139587402344, 134.42860412597656,
                       -138.71430206298828, 117.28569793701172]
    seriesDirectory = "Series 004 [MR - SAG RF FAST VOL FLIP 20]"
    lastSliceCorners = [[[81.05451202, 133.92860413, 116.78569794], [81.05451202, -122.07139587, 116.78569794]],
                        [[81.05451202, 133.92860413, -139.21429443], [81.05451202, -122.07139587, -139.21429443]]]
    filesToRemove = [
      "1.3.6.1.4.1.5962.99.1.3814087073.479799962.1489872804257.361.0.dcm",
      "1.3.6.1.4.1.5962.99.1.3814087073.479799962.1489872804257.362.0.dcm",
      "1.3.6.1.4.1.5962.99.1.3814087073.479799962.1489872804257.363.0.dcm",
      "1.3.6.1.4.1.5962.99.1.3814087073.479799962.1489872804257.364.0.dcm",
      "1.3.6.1.4.1.5962.99.1.3814087073.479799962.1489872804257.365.0.dcm",
      "1.3.6.1.4.1.5962.99.1.3814087073.479799962.1489872804257.366.0.dcm",
      "1.3.6.1.4.1.5962.99.1.3814087073.479799962.1489872804257.367.0.dcm",
      "1.3.6.1.4.1.5962.99.1.3814087073.479799962.1489872804257.368.0.dcm",
      "1.3.6.1.4.1.5962.99.1.3814087073.479799962.1489872804257.369.0.dcm",
      "1.3.6.1.4.1.5962.99.1.3814087073.479799962.1489872804257.370.0.dcm",
      "1.3.6.1.4.1.5962.99.1.3814087073.479799962.1489872804257.371.0.dcm",
      "1.3.6.1.4.1.5962.99.1.3814087073.479799962.1489872804257.372.0.dcm",
      "1.3.6.1.4.1.5962.99.1.3814087073.479799962.1489872804257.373.0.dcm",
      "1.3.6.1.4.1.5962.99.1.3814087073.479799962.1489872804257.374.0.dcm",
      "1.3.6.1.4.1.5962.99.1.3814087073.479799962.1489872804257.375.0.dcm",
      "1.3.6.1.4.1.5962.99.1.3814087073.479799962.1489872804257.376.0.dcm",
    ]

    try:

      print('Removing %d files from the middle of the series' % len(filesToRemove))
      for file in filesToRemove:
        filePath = os.path.join(dicomFilesDirectory, seriesDirectory, file)
        os.remove(filePath)

      #
      # insert the data into the database
      #
      self.delayDisplay("Switching to temp database directory")
      originalDatabaseDirectory = DICOMUtils.openTemporaryDatabase('tempDICOMDatabase')

      self.delayDisplay('Importing DICOM')
      mainWindow = slicer.util.mainWindow()
      mainWindow.moduleSelector().selectModule('DICOM')

      indexer = ctk.ctkDICOMIndexer()
      indexer.addDirectory(slicer.dicomDatabase, dicomFilesDirectory, None)
      indexer.waitForImportFinished()

      #
      # select the series
      #
      detailsPopup = slicer.modules.DICOMWidget.detailsPopup
      detailsPopup.open()
      # load the data by series UID
      detailsPopup.offerLoadables(seriesUID,'Series')
      detailsPopup.examineForLoading()
      loadable = list(detailsPopup.getAllSelectedLoadables().keys())[0]

      if len(loadable.warning) == 0:
        raise Exception("Expected warning about geometry issues due to missing slices!")

      #
      # load and correct for acquisition then check the geometry
      #
      scalarVolumePlugin = slicer.modules.dicomPlugins['DICOMScalarVolumePlugin']()
      volumeNode = scalarVolumePlugin.load(loadable)

      if not numpy.allclose(scalarVolumePlugin.acquisitionModeling.fixedCorners[-1], lastSliceCorners):
        raise Exception("Acquisition transform didn't fix slice corners!")

      self.delayDisplay('test_MissingSlices passed!')

    except Exception as e:
      import traceback
      traceback.print_exc()
      self.delayDisplay('Missing Slices Test caused exception!\n' + str(e))
      testPass = False

    self.delayDisplay("Restoring original database directory")
    mainWindow.moduleSelector().selectModule('DICOMReaders')

    return testPass
