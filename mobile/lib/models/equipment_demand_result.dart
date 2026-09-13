import 'party_demand_result.dart' show ReviewIssue, SkuBreakdownEntry;

/// Ergebnis von `POST /parties/{id}/admin/equipment-demand`
/// (`equipment_engine.domain.EquipmentDemandResult`). `ReviewIssue`/
/// `SkuBreakdownEntry` werden aus `party_demand_result.dart`
/// WIEDERVERWENDET statt dupliziert - die Equipment Engine importiert
/// dieselben Backend-Dataclasses verbatim aus `party_engine.domain`.

class EquipmentDemandContribution {
  final String source;
  final double amount;
  final String note;

  const EquipmentDemandContribution({
    required this.source,
    required this.amount,
    required this.note,
  });

  factory EquipmentDemandContribution.fromJson(Map<String, dynamic> json) => EquipmentDemandContribution(
        source: (json['source'] as String?) ?? '',
        amount: (json['amount'] as num?)?.toDouble() ?? 0.0,
        note: (json['note'] as String?) ?? '',
      );
}

class EquipmentDemand {
  final String itemId;
  final String name;
  final String unit;
  final double rawQuantity;
  final List<EquipmentDemandContribution> contributions;
  final double reservePct;
  final double quantityAfterReserve;
  final double existingQuantity;
  final double missingQuantity;
  final double finalRequiredQuantity;

  const EquipmentDemand({
    required this.itemId,
    required this.name,
    required this.unit,
    required this.rawQuantity,
    required this.contributions,
    required this.reservePct,
    required this.quantityAfterReserve,
    required this.existingQuantity,
    required this.missingQuantity,
    required this.finalRequiredQuantity,
  });

  bool get isCovered => missingQuantity <= 0;

  factory EquipmentDemand.fromJson(Map<String, dynamic> json) => EquipmentDemand(
        itemId: json['item_id'] as String,
        name: (json['name'] as String?) ?? '',
        unit: (json['unit'] as String?) ?? '',
        rawQuantity: (json['raw_quantity'] as num?)?.toDouble() ?? 0.0,
        contributions: (json['contributions'] as List? ?? [])
            .map((e) => EquipmentDemandContribution.fromJson((e as Map).cast<String, dynamic>()))
            .toList(),
        reservePct: (json['reserve_pct'] as num?)?.toDouble() ?? 0.0,
        quantityAfterReserve: (json['quantity_after_reserve'] as num?)?.toDouble() ?? 0.0,
        existingQuantity: (json['existing_quantity'] as num?)?.toDouble() ?? 0.0,
        missingQuantity: (json['missing_quantity'] as num?)?.toDouble() ?? 0.0,
        finalRequiredQuantity: (json['final_required_quantity'] as num?)?.toDouble() ?? 0.0,
      );
}

class EquipmentPurchasePlanItem {
  final String itemId;
  final String name;
  final double quantityNeeded;
  final String unit;
  final List<SkuBreakdownEntry> skuBreakdown;
  final double totalPurchasedQuantity;

  const EquipmentPurchasePlanItem({
    required this.itemId,
    required this.name,
    required this.quantityNeeded,
    required this.unit,
    required this.skuBreakdown,
    required this.totalPurchasedQuantity,
  });

  factory EquipmentPurchasePlanItem.fromJson(Map<String, dynamic> json) => EquipmentPurchasePlanItem(
        itemId: json['item_id'] as String,
        name: (json['name'] as String?) ?? '',
        quantityNeeded: (json['quantity_needed'] as num?)?.toDouble() ?? 0.0,
        unit: (json['unit'] as String?) ?? '',
        skuBreakdown: (json['sku_breakdown'] as List? ?? [])
            .map((e) => SkuBreakdownEntry.fromJson((e as Map).cast<String, dynamic>()))
            .toList(),
        totalPurchasedQuantity: (json['total_purchased_quantity'] as num?)?.toDouble() ?? 0.0,
      );
}

class EquipmentDemandResult {
  final Map<String, EquipmentDemand> demand;
  final List<EquipmentPurchasePlanItem> purchasePlan;
  final List<ReviewIssue> reviewIssues;

  const EquipmentDemandResult({
    required this.demand,
    required this.purchasePlan,
    required this.reviewIssues,
  });

  factory EquipmentDemandResult.fromJson(Map<String, dynamic> json) => EquipmentDemandResult(
        demand: (json['demand'] as Map? ?? {}).map(
          (key, value) => MapEntry(key as String, EquipmentDemand.fromJson((value as Map).cast<String, dynamic>())),
        ),
        purchasePlan: (json['purchase_plan'] as List? ?? [])
            .map((e) => EquipmentPurchasePlanItem.fromJson((e as Map).cast<String, dynamic>()))
            .toList(),
        reviewIssues: (json['review_issues'] as List? ?? [])
            .map((e) => ReviewIssue.fromJson((e as Map).cast<String, dynamic>()))
            .toList(),
      );
}
