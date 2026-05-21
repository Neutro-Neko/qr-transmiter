import Foundation
import AVFoundation
import Vision

func log(_ message: String) {
    fputs(message + "\n", stderr)
    fflush(stderr)
}

class QRScanner: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate {
    private let session = AVCaptureSession()
    private let queue = DispatchQueue(label: "com.qrscanner.cameraQueue")
    
    private var lastPayload: String? = nil
    private var lastPrintTime: Date = Date.distantPast
    
    func start() {
        let status = AVCaptureDevice.authorizationStatus(for: .video)
        switch status {
        case .authorized:
            self.setupCamera()
        case .notDetermined:
            log("Requesting camera access. Please approve the prompt if it appears.")
            let semaphore = DispatchSemaphore(value: 0)
            AVCaptureDevice.requestAccess(for: .video) { granted in
                if granted {
                    log("Camera access granted.")
                    self.setupCamera()
                } else {
                    log("Error: Camera access denied by user.")
                    exit(1)
                }
                semaphore.signal()
            }
            semaphore.wait()
        case .denied, .restricted:
            log("Error: Camera access is denied or restricted.")
            log("Please enable Camera access for your terminal or IDE in System Settings -> Privacy & Security -> Camera.")
            exit(1)
        @unknown default:
            log("Error: Unknown camera authorization status.")
            exit(1)
        }
    }
    
    private func setupCamera() {
        guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .unspecified) else {
            log("Error: No built-in camera found.")
            exit(1)
        }
        
        do {
            let input = try AVCaptureDeviceInput(device: device)
            if session.canAddInput(input) {
                session.addInput(input)
            } else {
                log("Error: Could not add camera input to session.")
                exit(1)
            }
            
            let output = AVCaptureVideoDataOutput()
            output.setSampleBufferDelegate(self, queue: queue)
            output.alwaysDiscardsLateVideoFrames = true
            
            output.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA]
            if session.canAddOutput(output) {
                session.addOutput(output)
            } else {
                log("Error: Could not add video output to session.")
                exit(1)
            }
            
            queue.async {
                self.session.startRunning()
                log("\n==================================================")
                log("Camera is active! Scanning QR codes continuously...")
                log("==================================================\n")
            }
        } catch {
            log("Error setting up camera: \(error.localizedDescription)")
            exit(1)
        }
    }
    
    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        guard let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        
        let request = VNDetectBarcodesRequest { [weak self] request, error in
            guard let self = self else { return }
            if let error = error {
                log("Detection error: \(error.localizedDescription)")
                return
            }
            
            guard let results = request.results as? [VNBarcodeObservation] else { return }
            
            for result in results {
                if result.symbology == .qr, let payload = result.payloadStringValue {
                    let now = Date()
                    // Only print if it's a new payload or if 150ms has passed since last print of the same payload
                    if payload != self.lastPayload || now.timeIntervalSince(self.lastPrintTime) > 0.15 {
                        self.lastPayload = payload
                        self.lastPrintTime = now
                        
                        // Print the raw payload to stdout on a single line
                        print(payload)
                        fflush(stdout)
                    }
                }
            }
        }
        
        request.symbologies = [.qr]
        
        let handler = VNImageRequestHandler(cvPixelBuffer: pixelBuffer, options: [:])
        do {
            try handler.perform([request])
        } catch {
            // Silently ignore individual frame processing errors
        }
    }
}

let scanner = QRScanner()
scanner.start()
RunLoop.main.run()
