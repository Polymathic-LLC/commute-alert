import SwiftUI
import WidgetKit

/// A trivial static widget so the extension also has a home/lock-screen widget.
/// S4 uses it for a rough look at the background-push refresh budget.
struct CommuteEntry: TimelineEntry {
    let date: Date
    let note: String
}

struct CommuteStaticProvider: TimelineProvider {
    func placeholder(in context: Context) -> CommuteEntry {
        CommuteEntry(date: .now, note: "S3 Probe")
    }

    func getSnapshot(in context: Context, completion: @escaping (CommuteEntry) -> Void) {
        completion(CommuteEntry(date: .now, note: "S3 Probe"))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<CommuteEntry>) -> Void) {
        let entry = CommuteEntry(date: .now, note: "reloaded \(Date.now.formatted(date: .omitted, time: .standard))")
        completion(Timeline(entries: [entry], policy: .atEnd))
    }
}

struct CommuteStaticWidget: Widget {
    var body: some WidgetConfiguration {
        StaticConfiguration(kind: "CommuteStaticWidget", provider: CommuteStaticProvider()) { entry in
            VStack(alignment: .leading, spacing: 2) {
                Text("S3 Probe").font(.caption2).bold()
                Text(entry.note).font(.caption2).foregroundStyle(.secondary)
            }
            .containerBackground(.fill.tertiary, for: .widget)
        }
        .configurationDisplayName("S3 Probe")
        .description("Static widget for background-push budget checks.")
        .supportedFamilies([.systemSmall, .accessoryRectangular])
    }
}
