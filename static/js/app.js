import { initPdfWorkspace } from './pdfWorkspace.js';
import { initCropTools } from './cropTools.js';
import { initTempFiles } from './tempFiles.js';
import { initUi } from './ui.js';
import { initImageProcessing } from './imageProcessing.js';
import { initManualRetouch } from './manualRetouch.js';
import { initCanvasRetouch } from './canvasRetouch.js';
import { initLineSegmentation } from './lineSegmentation.js';
import { initDiagnosticChat } from './diagnosticChat.js';
import { initSymbolDetection } from './symbolDetection.js';
import { initIgnoreZones } from './ignoreZones.js';
import { initEdgeConnectors } from './edgeConnectors.js';
import { initOcrPanel } from './ocrPanel.js';
import { TEMP_FILES_REFRESH_DELAY_MS } from './constants.js';

function getDomReferences() {
    return {
        ui: {
            overlay: document.getElementById('warningOverlay'),
            acceptWarningBtn: document.getElementById('acceptWarning'),
            appContent: document.getElementById('appContent'),
            tabButtons: document.querySelectorAll('.tab-btn'),
            tabPanels: document.querySelectorAll('.tab-panel'),
        },
        pdf: {
            fileInput: document.getElementById('fileInput'),
            uploadBtn: document.getElementById('uploadBtn'),
            uploadFromUploadsBtn: document.getElementById('uploadFromUploadsBtn'),
            uploadsModal: document.getElementById('uploadsModal'),
            uploadsList: document.getElementById('uploadsList'),
            uploadsCloseBtn: document.getElementById('uploadsCloseBtn'),
            uploadSaveOnLoadCheckbox: document.getElementById('uploadSaveOnLoadCheckbox'),
            imageCanvas: document.getElementById('imageCanvas'),
            canvasWrapper: document.querySelector('.canvas-wrapper'),
            prevPageBtn: document.getElementById('prevPageBtn'),
            nextPageBtn: document.getElementById('nextPageBtn'),
            currentPageLabel: document.getElementById('currentPageLabel'),
            totalPagesLabel: document.getElementById('totalPagesLabel'),
            pageInput: document.getElementById('pageInput'),
            zoomInBtn: document.getElementById('zoomInBtn'),
            zoomOutBtn: document.getElementById('zoomOutBtn'),
            zoomLabel: document.getElementById('zoomLabel'),
            filenamePill: document.getElementById('uploadedFilename'),
            exportDpiInput: document.getElementById('exportDpiInput'),
            exportMaxDpiValue: document.getElementById('exportMaxDpiValue'),
            exportMinDpiValue: document.getElementById('exportMinDpiValue'),
            exportDpiInfo: document.getElementById('exportDpiInfo'),
            exportDpiPreview: document.getElementById('exportDpiPreview'),
            exportDpiPreviewValue: document.getElementById('exportDpiPreviewValue'),
            uploadActionsSection: document.getElementById('uploadActionsSection'),
            exportDpiPreviewDimensions: document.getElementById('exportDpiPreviewDimensions'),
            dpiPresetRadios: document.getElementsByName('dpiPreset'),
            downloadPageBtn: document.getElementById('downloadPageBtn'),
            exportInfoLabel: document.getElementById('exportInfoLabel'),
            exportStatusLabel: document.getElementById('exportStatusLabel'),
        },
        ocr: {
            ocrRunBtn: document.getElementById('ocrRunBtn'),
            ocrResults: document.getElementById('ocrResults'), // legacy, may show raw JSON
            ocrResultsJson: document.getElementById('ocrResultsJson'),
            ocrAddRowBtn: document.getElementById('ocrAddRowBtn'),
            ocrSaveCorrectionsBtn: document.getElementById('ocrSaveCorrectionsBtn'),
            fileInput: document.getElementById('fileInput'),
        },
        maintenance: {
            cleanupBtn: document.getElementById('cleanupBtn'),
            tempFilesInfo: document.getElementById('tempFilesInfo'),
        },
        crop: {
            cropCanvas: document.getElementById('cropCanvas'),
            cropRulerLeft: document.getElementById('cropRulerLeft'),
            cropRulerRight: document.getElementById('cropRulerRight'),
            cropOverlay: document.getElementById('cropOverlay'),
            startCropBtn: document.getElementById('startCropBtn'),
            polygonCropBtn: document.getElementById('polygonCropBtn'),
            resetCropBtn: document.getElementById('resetCropBtn'),
            saveCropBtn: document.getElementById('saveCropBtn'),
            downloadCropBtn: document.getElementById('downloadCropBtn'),
            overwriteOriginalBtn: document.getElementById('overwriteOriginalBtn'),
            deskewBtn: document.getElementById('deskewBtn'),
            deskewManualBtn: document.getElementById('deskewManualBtn'),
            deskewManualControls: document.getElementById('deskewManualControls'),
            deskewAngleSlider: document.getElementById('deskewAngleSlider'),
            deskewAngleValue: document.getElementById('deskewAngleValue'),
            deskewApplyBtn: document.getElementById('deskewApplyBtn'),
            deskewCancelBtn: document.getElementById('deskewCancelBtn'),
            rotateLeftBtn: document.getElementById('rotateLeftBtn'),
            rotateRightBtn: document.getElementById('rotateRightBtn'),
            cropInstructions: document.getElementById('cropInstructions'),
            cropInstructionText: document.getElementById('cropInstructionText'),
            croppedPreview: document.getElementById('croppedPreview'),
            cropStats: document.getElementById('cropStats'),
            cropDimensions: document.getElementById('cropDimensions'),
            cropSize: document.getElementById('cropSize'),
            cropAspectRatio: document.getElementById('cropAspectRatio'),
            cropQuality: document.getElementById('cropQuality'),
            cropZoomInBtn: document.getElementById('cropZoomInBtn'),
            cropZoomOutBtn: document.getElementById('cropZoomOutBtn'),
            cropZoomResetBtn: document.getElementById('cropZoomResetBtn'),
            cropZoomLabel: document.getElementById('cropZoomLabel'),
        },
        processing: {
            historySelect: document.getElementById('processingHistorySelect'),
            loadPageBtn: document.getElementById('processingLoadPageBtn'),
            savePageBtn: document.getElementById('processingSavePageBtn'),
            loadFileBtn: document.getElementById('processingLoadFileBtn'),
            loadFileInput: document.getElementById('processingLoadFileInput'),
            originalImage: document.getElementById('processingOriginalImage'),
            originalPlaceholder: document.getElementById('processingOriginalPlaceholder'),
            resultImage: document.getElementById('processingResultImage'),
            resultPlaceholder: document.getElementById('processingResultPlaceholder'),
            applyBtn: document.getElementById('processingApplyBtn'),
            resetBtn: document.getElementById('processingResetBtn'),
            saveResultBtn: document.getElementById('processingSaveResultBtn'),
            downloadBtn: document.getElementById('processingDownloadBtn'),
            sendToRetouchBtn: document.getElementById('processingSendToRetouchBtn'),
            filterSelect: document.getElementById('processingFilterSelect'),
            manualControls: document.getElementById('processingManualControls'),
            adaptiveControls: document.getElementById('processingAdaptiveControls'),
            otsuInfo: document.getElementById('processingOtsuInfo'),
            thresholdSlider: document.getElementById('processingThresholdSlider'),
            thresholdValue: document.getElementById('processingThresholdValue'),
            adaptiveWindow: document.getElementById('processingAdaptiveWindow'),
            adaptiveWindowValue: document.getElementById('processingAdaptiveWindowValue'),
            adaptiveOffset: document.getElementById('processingAdaptiveOffset'),
            adaptiveOffsetValue: document.getElementById('processingAdaptiveOffsetValue'),
            statusLabel: document.getElementById('processingStatus'),
            zoomInBtn: document.getElementById('processingZoomInBtn'),
            zoomOutBtn: document.getElementById('processingZoomOutBtn'),
            zoomResetBtn: document.getElementById('processingZoomResetBtn'),
            zoomLabel: document.getElementById('processingZoomLabel'),
            historyList: document.getElementById('processingHistoryList'),
            historyClearBtn: document.getElementById('processingHistoryClearBtn'),
        },
        retouch: {
            loadBufferBtn: document.getElementById('retouchLoadBufferBtn'),
            loadDiskBtn: document.getElementById('retouchLoadDiskBtn'),
            loadFileInput: document.getElementById('retouchLoadFileInput'),
            clearBtn: document.getElementById('retouchClearBtn'),
            storeHistoryCheckbox: document.getElementById('retouchStoreHistory'),
            saveHistoryBtn: document.getElementById('retouchSaveHistoryBtn'),
            sourceImage: document.getElementById('retouchSourceImage'),
            sourcePlaceholder: document.getElementById('retouchSourcePlaceholder'),
            resultImage: document.getElementById('retouchResultImage'),
            resultPlaceholder: document.getElementById('retouchResultPlaceholder'),
            statusLabel: document.getElementById('retouchStatus'),
            autoFilterSelect: document.getElementById('retouchAutoFilterSelect'),
            applyAutoFilterBtn: document.getElementById('retouchApplyAutoFilterBtn'),
            undoBtn: document.getElementById('retouchUndoBtn'),
            downloadBtn: document.getElementById('retouchDownloadBtn'),
            // Kontrolki dla filtrów
            removeSmallControls: document.getElementById('retouchRemoveSmallControls'),
            removeSmallSlider: document.getElementById('retouchRemoveSmallSlider'),
            removeSmallValue: document.getElementById('retouchRemoveSmallValue'),
            morphOpenControls: document.getElementById('retouchMorphOpenControls'),
            morphOpenSlider: document.getElementById('retouchMorphOpenSlider'),
            morphOpenValue: document.getElementById('retouchMorphOpenValue'),
            morphCloseControls: document.getElementById('retouchMorphCloseControls'),
            morphCloseSlider: document.getElementById('retouchMorphCloseSlider'),
            morphCloseValue: document.getElementById('retouchMorphCloseValue'),
            medianControls: document.getElementById('retouchMedianControls'),
            medianSlider: document.getElementById('retouchMedianSlider'),
            medianValue: document.getElementById('retouchMedianValue'),
            denoiseControls: document.getElementById('retouchDenoiseControls'),
            denoiseSlider: document.getElementById('retouchDenoiseSlider'),
            denoiseValue: document.getElementById('retouchDenoiseValue'),
            // Przyciski zoom
            sourceZoomInBtn: document.getElementById('retouchSourceZoomInBtn'),
            sourceZoomOutBtn: document.getElementById('retouchSourceZoomOutBtn'),
            sourceZoomResetBtn: document.getElementById('retouchSourceZoomResetBtn'),
            sourceZoomLabel: document.getElementById('retouchSourceZoomLabel'),
            resultZoomInBtn: document.getElementById('retouchResultZoomInBtn'),
            resultZoomOutBtn: document.getElementById('retouchResultZoomOutBtn'),
            resultZoomResetBtn: document.getElementById('retouchResultZoomResetBtn'),
            resultZoomLabel: document.getElementById('retouchResultZoomLabel'),
            sourceStage: document.getElementById('retouchSourceStage'),
            resultStage: document.getElementById('retouchResultStage'),
        },
        canvasRetouch: {
            modeToggleBtn: document.getElementById('canvasModeToggleBtn'),
            modeLabel: document.getElementById('canvasModeLabel'),
            whiteBrushBtn: document.getElementById('canvasWhiteBrushBtn'),
            blackBrushBtn: document.getElementById('canvasBlackBrushBtn'),
            grayBrushBtn: document.getElementById('canvasGrayBrushBtn'),
            eraserBtn: document.getElementById('canvasEraserBtn'),
            brushSizeSlider: document.getElementById('canvasBrushSizeSlider'),
            brushSizeValue: document.getElementById('canvasBrushSizeValue'),
            grayControls: document.getElementById('canvasGrayControls'),
            graySlider: document.getElementById('canvasGraySlider'),
            grayValue: document.getElementById('canvasGrayValue'),
            grayPreview: document.getElementById('canvasGrayPreview'),
            undoBtn: document.getElementById('canvasUndoBtn'),
            redoBtn: document.getElementById('canvasRedoBtn'),
            binarizeBtn: document.getElementById('canvasBinarizeBtn'),
            invertBtn: document.getElementById('canvasInvertBtn'),
            loadFromCropBtn: document.getElementById('canvasLoadFromCropBtn'),
            loadFromRetouchBtn: document.getElementById('canvasLoadFromRetouchBtn'),
            loadFileBtn: document.getElementById('canvasLoadFileBtn'),
            loadFileInput: document.getElementById('canvasLoadFileInput'),
            resetBtn: document.getElementById('canvasResetBtn'),
            downloadBtn: document.getElementById('canvasDownloadBtn'),
            clearBtn: document.getElementById('canvasClearBtn'),
            statusLabel: document.getElementById('canvasRetouchStatus'),
            sourceImage: document.getElementById('canvasSourceImage'),
            sourcePlaceholder: document.getElementById('canvasSourcePlaceholder'),
            editorCanvas: document.getElementById('canvasRetouchEditor'),
            editorPlaceholder: document.getElementById('canvasEditorPlaceholder'),
            sourceZoomInBtn: document.getElementById('canvasSourceZoomInBtn'),
            sourceZoomOutBtn: document.getElementById('canvasSourceZoomOutBtn'),
            sourceZoomResetBtn: document.getElementById('canvasSourceZoomResetBtn'),
            sourceZoomLabel: document.getElementById('canvasSourceZoomLabel'),
            editorZoomInBtn: document.getElementById('canvasEditorZoomInBtn'),
            editorZoomOutBtn: document.getElementById('canvasEditorZoomOutBtn'),
            editorZoomResetBtn: document.getElementById('canvasEditorZoomResetBtn'),
            editorZoomLabel: document.getElementById('canvasEditorZoomLabel'),
        },
        lineSegmentation: {
            loadRetouchBtn: document.getElementById('lineSegLoadRetouchBtn'),
            loadToolsBtn: document.getElementById('lineSegLoadToolsBtn'),
            loadFileBtn: document.getElementById('lineSegLoadFileBtn'),
            loadFileInput: document.getElementById('lineSegLoadFileInput'),
            historyList: document.getElementById('lineSegHistoryList'),
            historyRefreshBtn: document.getElementById('lineSegHistoryRefreshBtn'),
            fixtureSelect: document.getElementById('lineSegFixtureSelect'),
            loadFixtureBtn: document.getElementById('lineSegLoadFixtureBtn'),
            fixtureInfo: document.getElementById('lineSegFixtureInfo'),
            runBtn: document.getElementById('lineSegRunBtn'),
            netlistBtn: document.getElementById('lineSegNetlistBtn'),
            netlistExportBtn: document.getElementById('lineSegSpiceExportBtn'),
            storeHistoryCheckbox: document.getElementById('lineSegStoreHistory'),
            debugCheckbox: document.getElementById('lineSegDebug'),
            binaryCheckbox: document.getElementById('lineSegBinary'),
            useConnectorRoiCheckbox: document.getElementById('lineSegUseConnectorRoi'),
            roiStatusLabel: document.getElementById('lineSegRoiStatus'),
            historyIdLabel: document.getElementById('lineSegHistoryIdLabel'),
            statusLabel: document.getElementById('lineSegStatus'),
            sourceImage: document.getElementById('lineSegSourceImage'),
            sourcePlaceholder: document.getElementById('lineSegSourcePlaceholder'),
            sourceStage: document.getElementById('lineSegSourceStage'),
            zoomInBtn: document.getElementById('lineSegZoomInBtn'),
            zoomOutBtn: document.getElementById('lineSegZoomOutBtn'),
            zoomResetBtn: document.getElementById('lineSegZoomResetBtn'),
            zoomLabel: document.getElementById('lineSegZoomLabel'),
            summaryLines: document.getElementById('lineSegSummaryLines'),
            summaryNodes: document.getElementById('lineSegSummaryNodes'),
            summaryTime: document.getElementById('lineSegSummaryTime'),
            summaryShape: document.getElementById('lineSegSummaryShape'),
            summaryBinary: document.getElementById('lineSegSummaryBinary'),
            summarySkeleton: document.getElementById('lineSegSummarySkeleton'),
            summaryFlagged: document.getElementById('lineSegSummaryFlagged'),
            debugList: document.getElementById('lineSegDebugList'),
            resultPre: document.getElementById('lineSegResultPre'),
                overlayCanvas: document.getElementById('lineSegOverlayCanvas'),
                symbolOverlayCanvas: document.getElementById('lineSegSymbolOverlay'),
                symbolOverlayToggle: document.getElementById('lineSegSymbolOverlayToggle'),
                symbolOverlayStatus: document.getElementById('lineSegSymbolStatus'),
            netlistSummaryNodes: document.getElementById('lineSegNetlistSummaryNodes'),
            netlistSummaryEdges: document.getElementById('lineSegNetlistSummaryEdges'),
            netlistSummaryEssential: document.getElementById('lineSegNetlistSummaryEssential'),
            netlistSummaryNonEssential: document.getElementById('lineSegNetlistSummaryNonEssential'),
            netlistSummaryEndpoints: document.getElementById('lineSegNetlistSummaryEndpoints'),
            netlistSummaryComponents: document.getElementById('lineSegNetlistSummaryComponents'),
            netlistSummaryCycles: document.getElementById('lineSegNetlistSummaryCycles'),
            netlistPre: document.getElementById('lineSegNetlistPre'),
            netlistStatus: document.getElementById('lineSegNetlistStatus'),
            symbolSection: document.getElementById('lineSegSymbolSection'),
            symbolStatus: document.getElementById('lineSegSymbolSummaryStatus'),
            symbolCount: document.getElementById('lineSegSymbolCount'),
            symbolDetector: document.getElementById('lineSegSymbolDetector'),
            symbolLatency: document.getElementById('lineSegSymbolLatency'),
            symbolCapturedAt: document.getElementById('lineSegSymbolCapturedAt'),
            symbolHistoryLink: document.getElementById('lineSegSymbolHistoryLink'),
            symbolTableWrapper: document.getElementById('lineSegSymbolTableWrapper'),
            symbolTableBody: document.getElementById('lineSegSymbolTableBody'),
            symbolTableEmpty: document.getElementById('lineSegSymbolEmpty'),
            connectorStatus: document.getElementById('lineSegConnectorStatus'),
            connectorRefreshBtn: document.getElementById('lineSegConnectorRefreshBtn'),
            connectorTableWrapper: document.getElementById('lineSegConnectorTableWrapper'),
            connectorTableBody: document.getElementById('lineSegConnectorTableBody'),
            connectorTableEmpty: document.getElementById('lineSegConnectorEmpty'),
            connectorHint: document.getElementById('lineSegConnectorHint'),
            spiceStatus: document.getElementById('lineSegSpiceStatus'),
            spicePre: document.getElementById('lineSegSpicePre'),
            spiceDownloadLink: document.getElementById('lineSegSpiceDownload'),
            componentSummary: document.getElementById('lineSegComponentSummary'),
            componentSummaryTableWrapper: document.getElementById('lineSegComponentTableWrapper'),
            componentSummaryTableBody: document.getElementById('lineSegComponentTableBody'),
            componentSummaryEmpty: document.getElementById('lineSegComponentEmpty'),
            overlayCanvas: document.getElementById('lineSegOverlayCanvas'),
            overlayToggle: document.getElementById('lineSegOverlayToggle'),
            logToggle: document.getElementById('lineSegLogToggle'),
            logList: document.getElementById('lineSegLogList'),
            logCopyBtn: document.getElementById('lineSegLogCopyBtn'),
            logClearBtn: document.getElementById('lineSegLogClearBtn'),
            logExport: document.getElementById('lineSegLogExport'),
            logCategory: document.getElementById('lineSegLogCategory'),
            logNoteInput: document.getElementById('lineSegLogNote'),
            logFeedback: document.getElementById('lineSegLogFeedback'),
            diagnosticPanel: document.getElementById('diagnosticChatPanel'),
            diagnosticStatus: document.getElementById('diagnosticChatStatus'),
            diagnosticFlaggedList: document.getElementById('diagnosticFlaggedList'),
            diagnosticStartBtn: document.getElementById('diagnosticStartChatBtn'),
            diagnosticChatBox: document.getElementById('diagnosticChatBox'),
            diagnosticChatLog: document.getElementById('diagnosticChatLog'),
            diagnosticChatInput: document.getElementById('diagnosticChatInput'),
            diagnosticChatSendBtn: document.getElementById('diagnosticChatSendBtn'),
            diagnosticChatCloseBtn: document.getElementById('diagnosticChatCloseBtn'),
        },
        ignoreZones: {
            canvas: document.getElementById('ignoreCanvas'),
            canvasWrapper: document.getElementById('ignoreCanvasWrapper'),
            modeRect: document.getElementById('ignoreModeRect'),
            modePoly: document.getElementById('ignoreModePoly'),
            modeBrush: document.getElementById('ignoreModeBrush'),
            brushSize: document.getElementById('ignoreBrushSize'),
            saveBtn: document.getElementById('ignoreSaveBtn'),
            loadBtn: document.getElementById('ignoreLoadBtn'),
            clearBtn: document.getElementById('ignoreClearBtn'),
            historyList: document.getElementById('ignoreHistoryList'),
            exportPre: document.getElementById('ignoreExport'),
            statusLabel: document.getElementById('ignoreStatus'),
            persistHistory: document.getElementById('ignorePersistHistory'),
        },
        diagnosticChat: {
            panel: document.getElementById('diagnosticChatPanel'),
            status: document.getElementById('diagnosticChatStatus'),
            flaggedList: document.getElementById('diagnosticFlaggedList'),
            startBtn: document.getElementById('diagnosticStartChatBtn'),
            chatBox: document.getElementById('diagnosticChatBox'),
            chatLog: document.getElementById('diagnosticChatLog'),
            chatInput: document.getElementById('diagnosticChatInput'),
            sendBtn: document.getElementById('diagnosticChatSendBtn'),
            closeBtn: document.getElementById('diagnosticChatCloseBtn'),
            highlightClearBtn: document.getElementById('diagnosticHighlightClearBtn'),
            isolateToggle: document.getElementById('diagnosticHighlightIsolate'),
        },
        symbolDetection: {
            statusLabel: document.getElementById('symbolStatus'),
            detectorSelect: document.getElementById('symbolDetectorSelect'),
            refreshBtn: document.getElementById('symbolRefreshBtn'),
            storeHistoryCheckbox: document.getElementById('symbolStoreHistory'),
            usePdfBtn: document.getElementById('symbolUsePdfBtn'),
            pdfInfo: document.getElementById('symbolPdfInfo'),
            pdfThumbnail: document.getElementById('symbolPdfThumbnail'),
            pdfThumbPlaceholder: document.getElementById('symbolPdfThumbPlaceholder'),
            segmentationInfo: document.getElementById('symbolSegInfo'),
            segmentationDetectBtn: document.getElementById('symbolSegDetectBtn'),
            segThumbnail: document.getElementById('symbolSegThumbnail'),
            segThumbPlaceholder: document.getElementById('symbolSegThumbPlaceholder'),
            fileInput: document.getElementById('symbolFileInput'),
            fileDetectBtn: document.getElementById('symbolFileDetectBtn'),
            fileNameLabel: document.getElementById('symbolFileName'),
            fileThumbnail: document.getElementById('symbolFileThumbnail'),
            fileThumbPlaceholder: document.getElementById('symbolFileThumbPlaceholder'),
            previewCanvas: document.getElementById('symbolPreviewCanvas'),
            previewFrame: document.getElementById('symbolPreviewFrame'),
            previewSourceLabel: document.getElementById('symbolPreviewSource'),
            previewOverlayToggle: document.getElementById('symbolPreviewOverlayToggle'),
            confidenceSlider: document.getElementById('symbolConfidenceSlider'),
            confidenceValue: document.getElementById('symbolConfidenceValue'),
            resultCount: document.getElementById('symbolResultCount'),
            resultDetector: document.getElementById('symbolResultDetector'),
            resultLatency: document.getElementById('symbolResultLatency'),
            resultSummary: document.getElementById('symbolResultSummary'),
            resultTableBody: document.getElementById('symbolResultTableBody'),
            rawOutputPre: document.getElementById('symbolRawOutput'),
            historyLink: document.getElementById('symbolHistoryLink'),
            historyList: document.getElementById('symbolHistoryList'),
            historyEmpty: document.getElementById('symbolHistoryEmpty'),
            historyRefreshBtn: document.getElementById('symbolHistoryRefreshBtn'),
        },
        edgeConnectors: {
            statusLabel: document.getElementById('edgeConnectorStatus'),
            pdfInfo: document.getElementById('edgeConnectorPdfInfo'),
            pageInfo: document.getElementById('edgeConnectorPageInfo'),
            selectionInfo: document.getElementById('edgeConnectorSelectionInfo'),
            usePdfBtn: document.getElementById('edgeConnectorUsePdfBtn'),
            form: document.getElementById('edgeConnectorForm'),
            edgeIdInput: document.getElementById('edgeConnectorEdgeId'),
            pageInput: document.getElementById('edgeConnectorPage'),
            labelInput: document.getElementById('edgeConnectorLabel'),
            netNameInput: document.getElementById('edgeConnectorNetName'),
            sheetIdInput: document.getElementById('edgeConnectorSheetId'),
            historyIdInput: document.getElementById('edgeConnectorHistoryId'),
            noteInput: document.getElementById('edgeConnectorNote'),
            geometryInput: document.getElementById('edgeConnectorGeometry'),
            geometryTemplateBtn: document.getElementById('edgeConnectorGeometryTemplateBtn'),
            previewCanvas: document.getElementById('edgeConnectorPreviewCanvas'),
            previewMockBtn: document.getElementById('edgeConnectorPreviewMockBtn'),
            previewLoadBtn: document.getElementById('edgeConnectorPreviewLoadBtn'),
            shrinkSlider: document.getElementById('edgeConnectorShrinkSlider'),
            shrinkValue: document.getElementById('edgeConnectorShrinkValue'),
            saveBtn: document.getElementById('edgeConnectorSaveBtn'),
            resetBtn: document.getElementById('edgeConnectorResetBtn'),
            countBadge: document.getElementById('edgeConnectorCount'),
            refreshBtn: document.getElementById('edgeConnectorRefreshBtn'),
            listBody: document.getElementById('edgeConnectorListBody'),
            listEmpty: document.getElementById('edgeConnectorListEmpty'),
            detailTitle: document.getElementById('edgeConnectorDetailTitle'),
            detailJson: document.getElementById('edgeConnectorDetailJson'),
            copyBtn: document.getElementById('edgeConnectorCopyBtn'),
        },
    };
}

const dom = getDomReferences();
let pdfApi;
let cropApi;
let processingApi;
let retouchApi;
let canvasRetouchApi;
let lineSegmentationApi;
let symbolDetectionApi;
let ocrApi;
let diagnosticChatApi;
let tempFilesApi;
let ignoreZonesApi;
let edgeConnectorsApi;
let lastPdfContext = null;

function handleShowApp() {
    if (!pdfApi || !cropApi) {
        return;
    }
    const context = lastPdfContext || pdfApi.getDocumentContext();
    if (context?.lastImageUrl) {
        cropApi.setSourceImage(context);
        symbolDetectionApi?.updatePdfContext?.(context);
        edgeConnectorsApi?.updatePdfContext?.(context);
    }
}

function handleTabChanged(tabId) {
    if (!tabId) {
        return;
    }
    if (tabId !== 'manual-retouch') {
        retouchApi?.onTabHidden?.();
    }
    if (tabId !== 'canvas-retouch') {
        canvasRetouchApi?.onTabHidden?.();
    }
    if (tabId !== 'line-segmentation') {
        lineSegmentationApi?.onTabHidden?.();
    }
    if (tabId !== 'symbol-detection') {
        symbolDetectionApi?.onTabHidden?.();
    }
    if (tabId !== 'edge-connectors') {
        edgeConnectorsApi?.onTabHidden?.();
    }

    if (tabId === 'crop-area') {
        cropApi?.onTabVisible?.();
    } else if (tabId === 'image-processing') {
        processingApi?.onTabVisible?.();
    } else if (tabId === 'manual-retouch') {
        retouchApi?.onTabVisible?.();
    } else if (tabId === 'canvas-retouch') {
        canvasRetouchApi?.onTabVisible?.();
    } else if (tabId === 'line-segmentation') {
        lineSegmentationApi?.onTabVisible?.();
    } else if (tabId === 'symbol-detection') {
        symbolDetectionApi?.onTabVisible?.();
    } else if (tabId === 'edge-connectors') {
        edgeConnectorsApi?.onTabVisible?.();
    } else if (tabId === 'diagnostics') {
        // Refresh readiness checklist when diagnostics tab is visible
        diagnosticChatApi?.refreshReadiness?.();
    }
}

initUi(dom.ui, {
    onShowApp: handleShowApp,
    onTabChanged: handleTabChanged,
});

diagnosticChatApi = initDiagnosticChat(dom.diagnosticChat);

cropApi = initCropTools(dom.crop, {
    getDocumentContext: () => pdfApi?.getDocumentContext() || {},
    onCropSaved: (entry) => {
        console.log('[app.js] onCropSaved callback wywołany, przekazuję do processingApi.handleCropSaved:', entry);
        processingApi?.handleCropSaved?.(entry);
    },
});

pdfApi = initPdfWorkspace(dom.pdf, {
    onImageRendered: (context) => {
        lastPdfContext = context;
        cropApi?.setSourceImage(context);
        if (symbolDetectionApi && typeof symbolDetectionApi.updatePdfContext === 'function') {
            symbolDetectionApi.updatePdfContext(context);
        }
        if (edgeConnectorsApi && typeof edgeConnectorsApi.updatePdfContext === 'function') {
            edgeConnectorsApi.updatePdfContext(context);
        }
    },
    onDocumentCleared: () => {
        lastPdfContext = null;
        cropApi?.clearSelection();
        processingApi?.resetOriginal?.();
        if (symbolDetectionApi && typeof symbolDetectionApi.updatePdfContext === 'function') {
            symbolDetectionApi.updatePdfContext(null);
        }
        edgeConnectorsApi?.updatePdfContext?.(null);
    },
});

processingApi = initImageProcessing(dom.processing, {
    getDocumentContext: pdfApi.getDocumentContext,
});

retouchApi = initManualRetouch(dom.retouch, {
    onHistorySaved: (entry) => {
        if (processingApi && typeof processingApi.ingestHistoryEntry === 'function') {
            processingApi.ingestHistoryEntry(entry);
        }
    },
    requestProcessingTransfer: () => {
        if (processingApi && typeof processingApi.transferResultToRetouch === 'function') {
            return processingApi.transferResultToRetouch({ silent: true });
        }
        return Promise.resolve(null);
    },
});

canvasRetouchApi = initCanvasRetouch(dom.canvasRetouch, {
    getRetouchBuffer: () => {
        // Zwraca ostatni wynik z zakładki "Automatyczny retusz"
        return retouchApi?.getProcessedResult ? retouchApi.getProcessedResult() : null;
    },
    getCropBuffer: () => {
        // Zwraca oryginalny crop z zakładki "Obróbka obrazu" (omija przetwarzanie)
        return processingApi?.getCurrentOriginal ? processingApi.getCurrentOriginal() : null;
    },
});

// Init ignore-zones module (frontend) - simple localStorage-backed editor for now
ignoreZonesApi = initIgnoreZones(dom.ignoreZones, {
    getPdfContext: pdfApi.getDocumentContext,
    getProcessingOriginal: processingApi?.getCurrentOriginal || (() => null),
    getCanvasRetouchImage: canvasRetouchApi?.getCanvasImage || (() => null),
});

lineSegmentationApi = initLineSegmentation(dom.lineSegmentation, {
    getProcessingOriginal: processingApi?.getCurrentOriginal || (() => null),
    getCanvasRetouchImage: canvasRetouchApi?.getCanvasImage || (() => null),
    diagnosticChat: diagnosticChatApi,
});

symbolDetectionApi = initSymbolDetection(dom.symbolDetection, {
    getPdfContext: pdfApi.getDocumentContext,
    getSegmentationContext: () => lineSegmentationApi?.getSourceContext?.() || null,
    ensureSegmentationSource: () => lineSegmentationApi?.ensureSourceUploaded?.() ?? Promise.resolve(false),
});

edgeConnectorsApi = initEdgeConnectors(dom.edgeConnectors, {
    getPdfContext: pdfApi.getDocumentContext,
    getSegmentationContext: () => lineSegmentationApi?.getSourceContext?.() || null,
});

// OCR panel initialization (simple wrapper around existing upload input)
ocrApi = initOcrPanel(dom.ocr);


if (typeof window !== 'undefined') {
    window.lineSegmentationApi = lineSegmentationApi;
    window.diagnosticChatApi = diagnosticChatApi;
}

if (
    symbolDetectionApi
    && typeof symbolDetectionApi.registerHistoryObserver === 'function'
    && lineSegmentationApi
    && typeof lineSegmentationApi.ingestSymbolDetectionHistory === 'function'
) {
    symbolDetectionApi.registerHistoryObserver((entry) => {
        lineSegmentationApi.ingestSymbolDetectionHistory(entry);
    });
}

if (
    lineSegmentationApi
    && typeof lineSegmentationApi.registerSourceObserver === 'function'
    && symbolDetectionApi
    && typeof symbolDetectionApi.updateSegmentationContext === 'function'
) {
    lineSegmentationApi.registerSourceObserver((context) => {
        symbolDetectionApi.updateSegmentationContext(context);
    });
    symbolDetectionApi.updateSegmentationContext(lineSegmentationApi.getSourceContext?.() || null);
}

if (
    lineSegmentationApi
    && typeof lineSegmentationApi.registerSourceObserver === 'function'
    && edgeConnectorsApi
    && typeof edgeConnectorsApi.updateSegmentationContext === 'function'
) {
    lineSegmentationApi.registerSourceObserver((context) => {
        edgeConnectorsApi.updateSegmentationContext(context);
    });
    edgeConnectorsApi.updateSegmentationContext(lineSegmentationApi.getSourceContext?.() || null);
}

if (processingApi && typeof processingApi.registerRetouchNotifier === 'function') {
    processingApi.registerRetouchNotifier((entry) => {
        retouchApi.handleBufferUpdate(entry);
        if (lineSegmentationApi && typeof lineSegmentationApi.handleRetouchUpdate === 'function') {
            lineSegmentationApi.handleRetouchUpdate(entry);
        }
    });
}

tempFilesApi = initTempFiles(dom.maintenance, {
    onCleanupSuccess: () => {
        pdfApi.resetDocument();
        cropApi.clearSelection();
        processingApi?.handleCleanup?.();
    },
});

pdfApi.onUploadComplete(() => {
    tempFilesApi.scheduleRefresh(TEMP_FILES_REFRESH_DELAY_MS);
});

tempFilesApi.refreshNow();
