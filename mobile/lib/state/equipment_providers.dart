import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/equipment_catalog_item.dart';
import '../models/equipment_demand_result.dart';
import '../models/equipment_inventory_item.dart';
import 'auth_providers.dart';
import 'providers.dart';

/// Equipment Engine (Mobile UI Phase) - Katalog-Browsing, Host-Inventar,
/// Party-Equipment-Bedarf.

/// Der volle Equipment-Katalog (59 Items) - in einem Rutsch geladen, wie
/// Foods `getDrinks`/`getFood` (keine Pagination bei dieser Größe nötig).
final equipmentCatalogProvider = FutureProvider<List<EquipmentCatalogItem>>((ref) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getEquipmentCatalog(token, onRefresh(ref));
});

final myEquipmentInventoryProvider = FutureProvider<List<EquipmentInventoryItem>>((ref) {
  final token = ref.watch(requiredAccessTokenProvider);
  return ref.watch(apiClientProvider).getMyEquipmentInventory(token, onRefresh(ref));
});

/// Bündelt Add/Update/Remove für das eigene Equipment-Inventar (mirrort
/// `ToggleOrganizerFollowNotifier`'s Follow/Unfollow-Bündelung).
class EquipmentInventoryNotifier extends AsyncNotifier<void> {
  @override
  Future<void> build() async {}

  Future<void> add(String equipmentItemId, {double quantity = 1.0}) async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      await ref.read(apiClientProvider).createEquipmentInventoryItem(
            token,
            onRefresh(ref),
            equipmentItemId: equipmentItemId,
            quantity: quantity,
          );
      state = const AsyncData(null);
      ref.invalidate(myEquipmentInventoryProvider);
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }

  Future<void> updateItem(
    String inventoryItemId, {
    double? quantity,
    String? condition,
    bool? available,
    String? notes,
  }) async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      await ref.read(apiClientProvider).updateEquipmentInventoryItem(
            token,
            onRefresh(ref),
            inventoryItemId,
            quantity: quantity,
            condition: condition,
            available: available,
            notes: notes,
          );
      state = const AsyncData(null);
      ref.invalidate(myEquipmentInventoryProvider);
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }

  Future<void> remove(String inventoryItemId) async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    try {
      await ref.read(apiClientProvider).deleteEquipmentInventoryItem(token, onRefresh(ref), inventoryItemId);
      state = const AsyncData(null);
      ref.invalidate(myEquipmentInventoryProvider);
    } catch (e) {
      state = AsyncError(e, StackTrace.current);
      rethrow;
    }
  }
}

final equipmentInventoryProvider =
    AsyncNotifierProvider<EquipmentInventoryNotifier, void>(EquipmentInventoryNotifier.new);

/// Zuletzt berechneter Equipment-Bedarf für eine Party (`null` = noch nicht
/// berechnet) - verbatim mirrort `ShoppingListNotifier` in
/// `admin_providers.dart`.
class EquipmentDemandNotifier extends FamilyAsyncNotifier<EquipmentDemandResult?, String> {
  @override
  Future<EquipmentDemandResult?> build(String arg) async => null;

  Future<void> compute() async {
    final token = ref.read(requiredAccessTokenProvider);
    state = const AsyncLoading();
    state = AsyncData(await ref.read(apiClientProvider).computeEquipmentDemand(arg, token, onRefresh(ref)));
  }
}

final equipmentDemandProvider =
    AsyncNotifierProvider.family<EquipmentDemandNotifier, EquipmentDemandResult?, String>(EquipmentDemandNotifier.new);

/// Navigations-Flag (mirrort `showFriendsProvider`) - `MyEquipmentScreen`
/// wird über eine Kachel auf `ProfileScreen` geöffnet.
final showMyEquipmentProvider = StateProvider<bool>((ref) => false);
