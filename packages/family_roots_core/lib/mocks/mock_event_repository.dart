import '../entities/entities.dart';
import '../repositories/event_repository.dart';

/// Mock implementation using hardcoded event data.
/// Replace with ApiEventRepository when backend is ready.
class MockEventRepository implements EventRepository {
  static const _mockEvents = [
    FamilyEvent(
      id: '1',
      title: 'Giỗ Tổ Dòng Họ',
      date: 'Mùng 10/03 ÂL',
      description: 'Họp mặt toàn thể con cháu họ Trần tại nhà thờ tổ chức lễ.',
      isLunar: true,
    ),
    FamilyEvent(
      id: '2',
      title: 'Đám Cưới Minh & Lan',
      date: '15/10/2026',
      description: 'Lễ thành hôn của Trần Minh và Nguyễn Lan lúc 9:00 AM.',
      isLunar: false,
    ),
    FamilyEvent(
      id: '3',
      title: 'Giỗ Cụ Khảo',
      date: '12/08 ÂL',
      description: 'Giỗ cụ Trần Khảo đời thứ 4.',
      isLunar: true,
    ),
  ];

  @override
  Future<List<FamilyEvent>> getUpcomingEvents() async {
    await Future.delayed(const Duration(milliseconds: 500));
    return _mockEvents;
  }

  @override
  Future<FamilyEvent> getEventById(String id) async {
    await Future.delayed(const Duration(milliseconds: 300));
    return _mockEvents.firstWhere((e) => e.id == id);
  }
}
