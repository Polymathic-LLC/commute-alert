import ActivityKit
import SwiftUI
import UIKit
import UserNotifications

struct ContentView: View {
    @EnvironmentObject private var model: ProbeModel
    @StateObject private var live = LiveActivityController()
    @State private var notifStatus = "unknown"
    @State private var activitiesEnabled = ActivityAuthorizationInfo().areActivitiesEnabled
    @State private var logLines = 0
    @State private var snapshotLines: [String] = []
    @State private var summaryLines: [String] = []
    @State private var exportNote = ""

    var body: some View {
        NavigationStack {
            List {
                Section("Live Activity") {
                    LabeledContent("State", value: model.activityState)
                    LabeledContent("Activities enabled", value: activitiesEnabled ? "yes" : "no")
                    LabeledContent("Live activities", value: "\(live.liveCount)")
                    Button("① Start locally (no push)") { live.startLocally() }
                    Button("② Local update") { live.bumpUpdate() }
                    Button("③ End", role: .destructive) { live.endActivity() }
                }

                Section("S4 — instrument") {
                    LabeledContent("App Group container",
                                   value: S4Log.containerURL == nil ? "MISSING" : "ok")
                    LabeledContent("Events logged", value: "\(logLines)")
                    Button("Refresh / snapshot") {
                        snapshotLines = live.snapshot()
                        logLines = S4Log.lineCount()
                        summaryLines = S4Log.summary()
                    }
                    Button("Export log to Files") {
                        if let url = S4Log.exportToDocuments() {
                            exportNote = "exported \(url.lastPathComponent)"
                        } else {
                            exportNote = "export FAILED"
                        }
                    }
                    if !exportNote.isEmpty {
                        Text(exportNote).font(.caption).foregroundStyle(.secondary)
                    }
                    ForEach(Array(snapshotLines.enumerated()), id: \.offset) { _, line in
                        Text(line).font(.system(.caption2, design: .monospaced))
                    }
                    ForEach(Array(summaryLines.enumerated()), id: \.offset) { _, line in
                        Text(line).font(.system(.caption2, design: .monospaced))
                    }
                }

                Section("S4 — experiments") {
                    Button("E5: start 6 activities (past the cap)") { live.startBatch(6) }
                    Button("E10: start with staleDate +120s") { live.startWithStaleDate(seconds: 120) }
                    Button("End ALL activities", role: .destructive) { live.endAll() }
                }

                Section("Notifications") {
                    LabeledContent("Authorization", value: notifStatus)
                    Button("Request permission") { requestNotifications() }
                }

                Section("Tokens — Copy, or read from the Xcode console") {
                    ForEach(ProbeModel.TokenKind.allCases) { kind in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(kind.rawValue)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Text(model.tokens[kind] ?? "— not issued yet —")
                                .font(.system(.footnote, design: .monospaced))
                                .textSelection(.enabled)
                                .lineLimit(4)
                            if let value = model.tokens[kind] {
                                Button("Copy") { UIPasteboard.general.string = value }
                                    .buttonStyle(.bordered)
                                    .controlSize(.small)
                            }
                        }
                        .padding(.vertical, 2)
                    }
                }

                Section("Log (newest first)") {
                    ForEach(Array(model.lines.enumerated().reversed()), id: \.offset) { _, line in
                        Text(line).font(.system(.caption2, design: .monospaced))
                    }
                }
            }
            .navigationTitle("S3 Probe")
            .onAppear {
                live.observePushToStartToken()
                // F4 fix: adopt activities started by ANY route, including ones
                // the backend started by push while the app was not running.
                live.observeAllActivities()
                snapshotLines = live.snapshot()
                logLines = S4Log.lineCount()
                summaryLines = S4Log.summary()
                refreshNotificationStatus()
            }
            .onReceive(NotificationCenter.default.publisher(for: UIApplication.didBecomeActiveNotification)) { _ in
                activitiesEnabled = ActivityAuthorizationInfo().areActivitiesEnabled
                refreshNotificationStatus()
            }
        }
    }

    private func requestNotifications() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, error in
            Task { @MainActor in
                model.log("notification permission: granted=\(granted) error=\(error?.localizedDescription ?? "none")")
                refreshNotificationStatus()
            }
        }
    }

    private func refreshNotificationStatus() {
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            Task { @MainActor in
                notifStatus = String(describing: settings.authorizationStatus)
            }
        }
    }
}
