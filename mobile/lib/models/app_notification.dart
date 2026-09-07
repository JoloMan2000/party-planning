/// Eine In-App-Benachrichtigung (`backend/app/schemas/notifications.py::NotificationPublic`).
/// Poll-basiert (siehe `notificationsProvider`) statt echtem Push - mirroring
/// die Backend-seitige TODO in `backend/app/routers/notifications.py`.
class AppNotification {
  final String id;
  final String? partyId;
  final String kind;
  final String message;
  final DateTime createdAt;
  final bool read;

  const AppNotification({
    required this.id,
    required this.partyId,
    required this.kind,
    required this.message,
    required this.createdAt,
    required this.read,
  });

  factory AppNotification.fromJson(Map<String, dynamic> json) => AppNotification(
        id: json['id'] as String,
        partyId: json['party_id'] as String?,
        kind: json['kind'] as String,
        message: json['message'] as String,
        createdAt: DateTime.parse(json['created_at'] as String),
        read: json['read'] as bool,
      );
}
