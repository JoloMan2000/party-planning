import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

/// Zeigt ein Bottom-Sheet zur Auswahl zwischen Fotobibliothek und Kamera -
/// gemeinsam genutzt vom Profilbild-Upload (`home_shell.dart`) und dem
/// Party-Cover-Bild-Upload (`party_detail_screen.dart`), damit beide Flows
/// identisch aussehen/funktionieren. Gibt `null` zurück, wenn der Nutzer
/// abbricht (Tap außerhalb / Zurück-Geste).
Future<ImageSource?> pickImageSource(BuildContext context) {
  return showModalBottomSheet<ImageSource>(
    context: context,
    builder: (context) => SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          ListTile(
            leading: const Icon(Icons.photo_library_outlined),
            title: const Text('Choose from library'),
            onTap: () => Navigator.pop(context, ImageSource.gallery),
          ),
          ListTile(
            leading: const Icon(Icons.photo_camera_outlined),
            title: const Text('Take a picture'),
            onTap: () => Navigator.pop(context, ImageSource.camera),
          ),
        ],
      ),
    ),
  );
}
