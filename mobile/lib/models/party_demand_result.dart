/// Ergebnis von `compute_party_demand()` (mirroring `render_shopping_list`'s
/// angezeigte Felder). `ingredientDemand`-Einträge enthalten zusätzlich
/// `family` (server-seitig angereichert, siehe
/// `backend/app/routers/admin_shopping_list.py::compute_shopping_list`).
class PartyDemandResult {
  final List<ItemDemandSummary> itemDemand;
  final Map<String, IngredientDemand> ingredientDemand;
  final List<PurchasePlanItem> purchasePlan;
  final List<ReviewIssue> reviewIssues;
  final double iceDemandKg;

  const PartyDemandResult({
    required this.itemDemand,
    required this.ingredientDemand,
    required this.purchasePlan,
    required this.reviewIssues,
    required this.iceDemandKg,
  });

  factory PartyDemandResult.fromJson(Map<String, dynamic> json) {
    return PartyDemandResult(
      itemDemand: (json['item_demand'] as List? ?? [])
          .map((e) => ItemDemandSummary.fromJson((e as Map).cast<String, dynamic>()))
          .toList(),
      ingredientDemand: (json['ingredient_demand'] as Map? ?? {}).map(
        (key, value) => MapEntry(
          key as String,
          IngredientDemand.fromJson((value as Map).cast<String, dynamic>()),
        ),
      ),
      purchasePlan: (json['purchase_plan'] as List? ?? [])
          .map((e) => PurchasePlanItem.fromJson((e as Map).cast<String, dynamic>()))
          .toList(),
      reviewIssues: (json['review_issues'] as List? ?? [])
          .map((e) => ReviewIssue.fromJson((e as Map).cast<String, dynamic>()))
          .toList(),
      iceDemandKg: (json['ice_demand_kg'] as num?)?.toDouble() ?? 0.0,
    );
  }
}

class ItemDemandSummary {
  final String itemId;
  final String itemName;
  final String itemType;
  final int supporters;
  final double expectedServings;

  const ItemDemandSummary({
    required this.itemId,
    required this.itemName,
    required this.itemType,
    required this.supporters,
    required this.expectedServings,
  });

  factory ItemDemandSummary.fromJson(Map<String, dynamic> json) {
    return ItemDemandSummary(
      itemId: json['item_id'] as String,
      itemName: json['item_name'] as String,
      itemType: (json['item_type'] as String?) ?? '',
      supporters: (json['supporters'] as num?)?.toInt() ?? 0,
      expectedServings: (json['expected_servings'] as num?)?.toDouble() ?? 0.0,
    );
  }
}

class IngredientDemandContribution {
  final String sourceItemId;
  final String sourceItemName;
  final double amount;
  final String unit;

  const IngredientDemandContribution({
    required this.sourceItemId,
    required this.sourceItemName,
    required this.amount,
    required this.unit,
  });

  factory IngredientDemandContribution.fromJson(Map<String, dynamic> json) {
    return IngredientDemandContribution(
      sourceItemId: json['source_item_id'] as String,
      sourceItemName: (json['source_item_name'] as String?) ?? '',
      amount: (json['amount'] as num?)?.toDouble() ?? 0.0,
      unit: (json['unit'] as String?) ?? '',
    );
  }
}

class IngredientDemand {
  final String ingredientId;
  final String name;
  final String unit;
  final double rawQuantity;
  final List<IngredientDemandContribution> contributions;
  final double reservePct;
  final double quantityAfterReserve;
  final String family;

  const IngredientDemand({
    required this.ingredientId,
    required this.name,
    required this.unit,
    required this.rawQuantity,
    required this.contributions,
    required this.reservePct,
    required this.quantityAfterReserve,
    required this.family,
  });

  factory IngredientDemand.fromJson(Map<String, dynamic> json) {
    return IngredientDemand(
      ingredientId: json['ingredient_id'] as String,
      name: (json['name'] as String?) ?? '',
      unit: (json['unit'] as String?) ?? '',
      rawQuantity: (json['raw_quantity'] as num?)?.toDouble() ?? 0.0,
      contributions: (json['contributions'] as List? ?? [])
          .map((e) => IngredientDemandContribution.fromJson((e as Map).cast<String, dynamic>()))
          .toList(),
      reservePct: (json['reserve_pct'] as num?)?.toDouble() ?? 0.0,
      quantityAfterReserve: (json['quantity_after_reserve'] as num?)?.toDouble() ?? 0.0,
      family: (json['family'] as String?) ?? '',
    );
  }
}

class SkuBreakdownEntry {
  final double size;
  final String unit;
  final int count;
  final String packLabel;

  const SkuBreakdownEntry({
    required this.size,
    required this.unit,
    required this.count,
    required this.packLabel,
  });

  factory SkuBreakdownEntry.fromJson(Map<String, dynamic> json) {
    return SkuBreakdownEntry(
      size: (json['size'] as num?)?.toDouble() ?? 0.0,
      unit: (json['unit'] as String?) ?? '',
      count: (json['count'] as num?)?.toInt() ?? 0,
      packLabel: (json['pack_label'] as String?) ?? '',
    );
  }
}

class PurchasePlanItem {
  final String ingredientId;
  final String name;
  final double quantityNeeded;
  final String unit;
  final List<SkuBreakdownEntry> skuBreakdown;
  final double totalPurchasedQuantity;

  const PurchasePlanItem({
    required this.ingredientId,
    required this.name,
    required this.quantityNeeded,
    required this.unit,
    required this.skuBreakdown,
    required this.totalPurchasedQuantity,
  });

  factory PurchasePlanItem.fromJson(Map<String, dynamic> json) {
    return PurchasePlanItem(
      ingredientId: json['ingredient_id'] as String,
      name: (json['name'] as String?) ?? '',
      quantityNeeded: (json['quantity_needed'] as num?)?.toDouble() ?? 0.0,
      unit: (json['unit'] as String?) ?? '',
      skuBreakdown: (json['sku_breakdown'] as List? ?? [])
          .map((e) => SkuBreakdownEntry.fromJson((e as Map).cast<String, dynamic>()))
          .toList(),
      totalPurchasedQuantity: (json['total_purchased_quantity'] as num?)?.toDouble() ?? 0.0,
    );
  }
}

class ReviewIssue {
  final String guestName;
  final String rawText;
  final String issueType;
  final String message;

  const ReviewIssue({
    required this.guestName,
    required this.rawText,
    required this.issueType,
    required this.message,
  });

  factory ReviewIssue.fromJson(Map<String, dynamic> json) {
    return ReviewIssue(
      guestName: (json['guest_name'] as String?) ?? '',
      rawText: (json['raw_text'] as String?) ?? '',
      issueType: (json['issue_type'] as String?) ?? '',
      message: (json['message'] as String?) ?? '',
    );
  }
}
