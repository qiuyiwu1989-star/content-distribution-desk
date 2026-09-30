import AppKit
import WebKit

final class DistributionApp: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    private let homeURL = URL(string: "http://127.0.0.1:4318/")!
    private var window: NSWindow!
    private var webView: WKWebView!
    private var server: Process?
    private var serverLog: FileHandle?
    private var attempts = 0
    private var closing = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        let frame = NSRect(x: 0, y: 0, width: 1160, height: 780)
        window = NSWindow(contentRect: frame, styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "内容分发台"
        window.minSize = NSSize(width: 760, height: 560)
        window.center()
        window.isReleasedWhenClosed = false
        let config = WKWebViewConfiguration()
        config.defaultWebpagePreferences.allowsContentJavaScript = true
        webView = WKWebView(frame: frame, configuration: config)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        window.contentView = webView
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        showMessage("正在启动内容分发台…")
        checkServer(startIfMissing: true)
        makeMenu()
    }

    private func makeMenu() {
        let menu = NSMenu()
        let app = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "关于内容分发台", action: #selector(showAbout), keyEquivalent: "")
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(withTitle: "退出内容分发台", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        app.submenu = appMenu
        menu.addItem(app)
        let view = NSMenuItem()
        let viewMenu = NSMenu(title: "显示")
        viewMenu.addItem(withTitle: "刷新", action: #selector(reloadPage), keyEquivalent: "r")
        view.submenu = viewMenu
        menu.addItem(view)
        NSApp.mainMenu = menu
    }

    @objc private func showAbout() {
        let alert = NSAlert()
        alert.messageText = "内容分发台"
        alert.informativeText = "本机应用。成品、任务与附件保存在原项目的数据目录。关闭应用会停止它启动的本机服务。"
        alert.runModal()
    }
    @objc private func reloadPage() { webView.reload() }

    private func projectURL() -> URL? {
        let project = Bundle.main.resourceURL!.appendingPathComponent("Project", isDirectory: true)
        return FileManager.default.isExecutableFile(atPath: project.appendingPathComponent(".venv/bin/python").path) &&
            FileManager.default.fileExists(atPath: project.appendingPathComponent("server.py").path) ? project : nil
    }
    private func dataURL() -> URL {
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        return support.appendingPathComponent("内容分发台/data", isDirectory: true)
    }

    private func checkServer(startIfMissing: Bool) {
        var request = URLRequest(url: homeURL.appendingPathComponent("api/state"))
        request.timeoutInterval = 2
        URLSession.shared.dataTask(with: request) { [weak self] data, response, _ in
            DispatchQueue.main.async {
                guard let self = self, !self.closing else { return }
                if let http = response as? HTTPURLResponse, http.statusCode == 200,
                   let data = data,
                   let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   json["packages"] is [Any], json["tasks"] is [Any], json["accounts"] is [Any] {
                    self.webView.load(URLRequest(url: self.homeURL))
                } else if startIfMissing {
                    self.startServer()
                } else {
                    self.attempts += 1
                    if self.attempts < 60 {
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { self.checkServer(startIfMissing: false) }
                    } else {
                        self.showMessage("分发台启动超时。请检查项目环境或应用日志。")
                    }
                }
            }
        }.resume()
    }

    private func startServer() {
        guard let project = projectURL() else {
            showMessage("找不到项目或 Python 环境。请重新构建并安装应用。")
            return
        }
        let logURL = dataURL().appendingPathComponent("mac-app.log")
        try? FileManager.default.createDirectory(at: dataURL(), withIntermediateDirectories: true)
        FileManager.default.createFile(atPath: logURL.path, contents: nil)
        let log = try? FileHandle(forWritingTo: logURL)
        _ = try? log?.seekToEnd()
        serverLog = log
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/bin/zsh")
        task.arguments = ["-f", project.appendingPathComponent("mac-app/run-server.sh").path]
        task.currentDirectoryURL = project
        var environment = ProcessInfo.processInfo.environment
        environment["PORT"] = "4318"
        environment["DESK_DATA_DIR"] = dataURL().path
        let runtime = dataURL().deletingLastPathComponent().appendingPathComponent("runtime")
        environment["DESK_SAU_ROOT"] = runtime.appendingPathComponent("social-auto-upload").path
        environment["DESK_SAU_PYTHON"] = runtime.appendingPathComponent(".sau-venv/bin/python").path
        task.environment = environment
        if let log = log { task.standardOutput = log; task.standardError = log }
        do {
            try task.run()
            server = task
            attempts = 0
            checkServer(startIfMissing: false)
        } catch {
            showMessage("无法启动本机服务：\(error.localizedDescription)")
        }
    }

    private func showMessage(_ message: String) {
        let escaped = message.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;")
        webView.loadHTMLString("<html lang='zh-CN'><meta charset='utf-8'><style>body{font:16px -apple-system;background:#f6f7f9;color:#284b40;display:grid;place-items:center;height:100vh;margin:0}div{padding:35px;background:white;border-radius:12px;box-shadow:0 10px 40px #284b4014}</style><div>\(escaped)</div></html>", baseURL: nil)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) {
        closing = true
        if let task = server, task.isRunning { task.terminate() }
        try? serverLog?.close()
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        if url.scheme == "http", url.host == "127.0.0.1", url.port == 4318 {
            if url.path == "/api/backup" || (url.path.hasPrefix("/api/tasks/") && url.path.hasSuffix("/bundle")) {
                decisionHandler(.download)
            } else {
                decisionHandler(.allow)
            }
        } else if ["https", "http"].contains(url.scheme ?? "") {
            NSWorkspace.shared.open(url)
            decisionHandler(.cancel)
        } else { decisionHandler(.cancel) }
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) { download.delegate = self }
    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) { download.delegate = self }
    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        let downloads = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first!
        let original = URL(fileURLWithPath: suggestedFilename)
        var destination = downloads.appendingPathComponent(suggestedFilename)
        var number = 2
        while FileManager.default.fileExists(atPath: destination.path) {
            destination = downloads.appendingPathComponent("\(original.deletingPathExtension().lastPathComponent)-\(number).\(original.pathExtension)")
            number += 1
        }
        completionHandler(destination)
    }
    func downloadDidFinish(_ download: WKDownload) { NSSound.beep() }
    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) { showMessage("下载失败：\(error.localizedDescription)") }

    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.beginSheetModal(for: window) { response in completionHandler(response == .OK ? panel.urls : nil) }
    }
}

let application = NSApplication.shared
let delegate = DistributionApp()
application.delegate = delegate
application.run()
