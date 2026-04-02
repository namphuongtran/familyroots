import '../entities/entities.dart';

/// Abstract repository contract for event operations.
abstract class EventRepository {
  Future<List<FamilyEvent>> getUpcomingEvents();
  Future<FamilyEvent> getEventById(String id);
}
