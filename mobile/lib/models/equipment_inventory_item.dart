/// Ein Host-Equipment-Inventar-Eintrag
/// (`backend/app/schemas/equipment.py::EquipmentInventoryItemPublic`).
class EquipmentInventoryItem {
  final String id;
  final String ownerUserId;
  final String equipmentItemId;
  final double quantity;
  final String condition;
  final bool available;
  final String notes;

  const EquipmentInventoryItem({
    required this.id,
    required this.ownerUserId,
    required this.equipmentItemId,
    required this.quantity,
    required this.condition,
    required this.available,
    required this.notes,
  });

  factory EquipmentInventoryItem.fromJson(Map<String, dynamic> json) => EquipmentInventoryItem(
        id: json['id'] as String,
        ownerUserId: json['owner_user_id'] as String,
        equipmentItemId: json['equipment_item_id'] as String,
        quantity: (json['quantity'] as num?)?.toDouble() ?? 1.0,
        condition: (json['condition'] as String?) ?? '',
        available: (json['available'] as bool?) ?? true,
        notes: (json['notes'] as String?) ?? '',
      );
}
