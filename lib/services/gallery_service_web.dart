// ignore: avoid_web_libraries_in_flutter
import 'dart:html' as html;

/// Triggers a direct browser download of [url] saved as [fileName].
void triggerBrowserDownload(String url, String fileName) {
  final anchor = html.AnchorElement(href: url)
    ..setAttribute("download", fileName)
    ..style.display = "none";
  html.document.body?.children.add(anchor);
  anchor.click();
  anchor.remove();
}
