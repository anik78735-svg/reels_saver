/// Stub used on mobile/desktop builds where dart:html is unavailable.
/// This function is never actually called on those platforms because
/// GalleryService checks kIsWeb first.
void triggerBrowserDownload(String url, String fileName) {
  throw UnsupportedError("Browser download is only available on web.");
}
