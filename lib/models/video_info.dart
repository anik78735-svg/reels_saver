class VideoInfo {
  final String videoUrl;
  final String? thumbnail;
  final String? caption;
  final String? title;

  VideoInfo({
    required this.videoUrl,
    this.thumbnail,
    this.caption,
    this.title,
  });

  factory VideoInfo.fromJson(Map<String, dynamic> json) {
    return VideoInfo(
      videoUrl: json['video_url'] ?? json['download_url'] ?? '',
      thumbnail: json['thumbnail'],
      caption: json['caption'] ?? json['description'],
      title: json['title'],
    );
  }
}
