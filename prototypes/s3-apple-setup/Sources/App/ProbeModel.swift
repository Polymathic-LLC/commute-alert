import Combine
import Foundation
import OSLog
import UIKit

/// Single place every token and lifecycle event lands, so a human can read them
/// off the screen (Copy buttons) or the Xcode console, and S2/S4 can correlate.
@MainActor
final class ProbeModel: ObservableObject {
    static let shared = ProbeModel()

    private let logger = Logger(subsystem: "com.polymathic.commutealert.s3probe", category: "probe")
    private let iso = ISO8601DateFormatter()

    enum TokenKind: String, CaseIterable, Identifiable {
        case pushToStart = "LIVE ACTIVITY push-to-start token"
        case activity    = "LIVE ACTIVITY per-activity push token"
        case apnsDevice  = "APNs device token (alert / background)"
        var id: String { rawValue }
    }

    @Published private(set) var tokens: [TokenKind: String] = [:]
    @Published private(set) var activityState: String = "none"
    @Published private(set) var lines: [String] = []

    private init() {}

    func set(_ kind: TokenKind, _ hex: String) {
        tokens[kind] = hex
        log("\(kind.rawValue) =\n\(hex)")
    }

    func setActivityState(_ state: String) {
        activityState = state
        log("activity state -> \(state)")
    }

    func log(_ message: String) {
        let stamped = "\(iso.string(from: .now))  \(message)"
        lines.append(stamped)
        logger.log("\(message, privacy: .public)")
        print("[S3] \(stamped)")
    }

    static func hex(_ data: Data) -> String {
        data.map { String(format: "%02x", $0) }.joined()
    }
}
