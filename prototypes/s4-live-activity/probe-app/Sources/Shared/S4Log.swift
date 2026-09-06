import Foundation

/// S4 instrumentation. Append-only NDJSON in the shared App Group container.
///
/// WHY THIS EXISTS AT ALL
/// ----------------------
/// Most of S4's questions are answered better by asking a person to look at the
/// Lock Screen than by building a pipeline, and the ones that can be are. Three
/// cannot:
///
///   * the update-budget ceiling — finding where pushes stop landing means many
///     sends over hours, and nobody can watch a Lock Screen through that;
///   * `apns-collapse-id` under 1-second succession — too fast to eyeball;
///   * the per-activity push token of an activity the *backend* started — the
///     app is the only thing that ever sees it.
///
/// This file is deliberately the smallest thing that covers those three. An
/// earlier design had an HTTP collector, local-network entitlements and a live
/// upload panel; all of it existed only to avoid asking a human, and all of it
/// was cut.
///
/// THE TWO-PROCESS PROBLEM
/// -----------------------
/// The Live Activity view body runs in the **widget extension** process, not the
/// app. It cannot touch `ProbeModel` (an app-process singleton). A file in the
/// shared App Group container is the only channel between them, which is why
/// this is a plain function writing bytes rather than anything nicer.
///
/// Appends use POSIX `O_APPEND`: each line is a single `write(2)` well under
/// `PIPE_BUF`, so a write from the widget process and one from the app process
/// cannot interleave. `FileHandle` + `seekToEndOfFile` would *not* be safe here
/// — that is two syscalls, and these two processes genuinely do run at once.
///
/// Throwaway prototype code. Not a production telemetry design.
enum S4Log {
    static let appGroup = "group.com.polymathic.commutealert.s3probe"
    static let filename = "s4-events.ndjson"

    /// Nil when the App Group container is not provisioned — which "the app
    /// launched fine" does *not* prove. Surfaced in the UI rather than silently
    /// swallowed: an instrument that quietly writes nowhere is worse than no
    /// instrument, because it produces confident empty results.
    static var containerURL: URL? {
        FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroup)
    }

    static var fileURL: URL? {
        containerURL?.appendingPathComponent(filename)
    }

    /// One event. `src` names the observer, so a finding can name its instrument:
    /// `widget` = I1 (render log), `app` = I2 (contentUpdates) / I3 (snapshot).
    static func write(src: String, event: String, fields: [String: String] = [:]) {
        guard let url = fileURL else { return }

        var row: [String: String] = [
            "t": iso.string(from: Date()),
            "mono": String(format: "%.3f", ProcessInfo.processInfo.systemUptime),
            "src": src,
            "event": event,
        ]
        row.merge(fields) { _, new in new }

        guard let data = try? JSONSerialization.data(withJSONObject: row,
                                                     options: [.sortedKeys]),
              let json = String(data: data, encoding: .utf8) else { return }
        let line = json + "\n"

        line.withCString { cstr in
            let fd = open(url.path, O_WRONLY | O_APPEND | O_CREAT, 0o644)
            guard fd >= 0 else { return }
            _ = Darwin.write(fd, cstr, strlen(cstr))
            close(fd)
        }
    }

    /// I1, the render log. Called from the Live Activity view body in the widget
    /// process. `headline` carries the experiment id and sequence number the
    /// sender put there, so `sent seq` ∩ `observed seq` is computable without
    /// trusting any clock but ours.
    ///
    /// A render is not the same event as an update — iOS may coalesce renders,
    /// may not render while the screen is off, and may re-render with unchanged
    /// content. So this instrument is calibrated (PROTOCOL.md E0) before any
    /// number derived from it is reported.
    static func render(surface: String,
                       routeName: String,
                       stopName: String,
                       v: Int,
                       displayStatus: String,
                       headline: String,
                       minutesToDeparture: Int?,
                       updatedAt: Date) {
        write(src: "widget", event: "render", fields: [
            "surface": surface,
            "routeName": routeName,
            "stopName": stopName,
            "v": String(v),
            "displayStatus": displayStatus,
            "headline": headline,
            "minutes": minutesToDeparture.map(String.init) ?? "",
            // Round-tripping the decoded Date is how we check ActivityKit's push
            // date-decoding strategy, which S2 could not determine without
            // sending. A wrong strategy surfaces here as a 2001 or 1970 date
            // rather than as a silent no-op.
            "updatedAt": iso.string(from: updatedAt),
        ])
    }

    static func read() -> String {
        guard let url = fileURL,
              let text = try? String(contentsOf: url, encoding: .utf8) else { return "" }
        return text
    }

    static func lineCount() -> Int {
        let text = read()
        return text.isEmpty ? 0 : text.split(separator: "\n").count
    }

    static func clear() {
        guard let url = fileURL else { return }
        try? FileManager.default.removeItem(at: url)
        write(src: "app", event: "log_cleared")
    }

    /// Copy the log into Documents, where `UIFileSharingEnabled` exposes it to
    /// the Files app so it can be AirDropped to the Mac. This is what replaced
    /// the HTTP collector: one tap and one AirDrop, instead of a local-network
    /// permission prompt and a server that must be up whenever the phone talks.
    @discardableResult
    static func exportToDocuments() -> URL? {
        guard let src = fileURL else { return nil }
        let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let stamp = filenameStamp.string(from: Date())
        let dst = docs.appendingPathComponent("s4-events-\(stamp).ndjson")
        try? FileManager.default.removeItem(at: dst)
        do {
            try FileManager.default.copyItem(at: src, to: dst)
            return dst
        } catch {
            return nil
        }
    }

    /// Compact on-device summary, so the common case needs no file transfer at
    /// all: the human reads one screen and screenshots it. Groups observed
    /// renders by the experiment tag at the front of each headline and lists the
    /// sequence numbers seen, deduplicated.
    static func summary() -> [String] {
        let lines = read().split(separator: "\n")
        var seen: [String: Set<String>] = [:]
        var order: [String] = []

        for line in lines {
            guard let data = line.data(using: .utf8),
                  let row = try? JSONSerialization.jsonObject(with: data) as? [String: String],
                  row["event"] == "render",
                  let headline = row["headline"] else { continue }
            // Headlines look like: "S4 E2 b3 s041 60s"  → tag "E2 b3", seq "041"
            let parts = headline.split(separator: " ").map(String.init)
            guard parts.count >= 3 else { continue }
            let tag = parts.prefix(3).joined(separator: " ")
            let seq = parts.count > 3 ? parts[3] : "-"
            if seen[tag] == nil { order.append(tag) }
            seen[tag, default: []].insert(seq)
        }

        return order.map { tag in
            let seqs = seen[tag]!.sorted()
            return "\(tag): \(seqs.count) seen — \(seqs.joined(separator: ","))"
        }
    }

    private static let iso: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    private static let filenameStamp: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyyMMdd-HHmmss"
        return f
    }()
}
