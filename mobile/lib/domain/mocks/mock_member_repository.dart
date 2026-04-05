import '../entities/entities.dart';
import '../repositories/member_repository.dart';

/// Mock implementation using hardcoded data.
/// Replace with ApiMemberRepository when backend is ready.
class MockMemberRepository implements MemberRepository {
  static const _mockMembers = [
    MemberModel(id: '1', name: 'Trần Văn Khảo', generation: 1, branch: '1', birthYear: 1910, deathYear: 1985, biography: 'Cụ tổ dòng họ Trần Văn tại làng An Phú.', gender: 'male'),
    MemberModel(id: '2', name: 'Trần Văn Minh', generation: 2, branch: '1', birthYear: 1950, biography: 'Con trưởng cụ Khảo, người gìn giữ gia phả.', gender: 'male'),
    MemberModel(id: '3', name: 'Trần Văn Bảo', generation: 3, branch: '1', birthYear: 1978, biography: 'Cháu trưởng dòng họ.', gender: 'male'),
    MemberModel(id: '4', name: 'Trần Thị Hằng', generation: 3, branch: '1', birthYear: 1982, gender: 'female'),
    MemberModel(id: '5', name: 'Trần Văn Hùng', generation: 2, branch: '2', birthYear: 1955, gender: 'male'),
    MemberModel(id: '6', name: 'Trần Thị Mai', generation: 2, branch: '1', birthYear: 1958, gender: 'female'),
    MemberModel(id: '7', name: 'Trần Văn Đại', generation: 3, branch: '2', birthYear: 1985, gender: 'male'),
    MemberModel(id: '8', name: 'Trần Văn Phúc', generation: 4, branch: '1', birthYear: 2005, gender: 'male'),
    MemberModel(id: '9', name: 'Trần Thị Lan', generation: 4, branch: '1', birthYear: 2008, gender: 'female'),
    MemberModel(id: '10', name: 'Trần Văn Tèo', generation: 3, branch: '2', birthYear: 1990, gender: 'male'),
  ];

  static const _mockRelationships = [
    Relationship(memberId: '2', relatedMemberId: '1', relationType: 'father', relatedMemberName: 'Trần Văn Khảo'),
    Relationship(memberId: '2', relatedMemberId: '6', relationType: 'wife', relatedMemberName: 'Trần Thị Mai'),
    Relationship(memberId: '2', relatedMemberId: '3', relationType: 'son', relatedMemberName: 'Trần Văn Bảo'),
    Relationship(memberId: '2', relatedMemberId: '4', relationType: 'daughter', relatedMemberName: 'Trần Thị Hằng'),
  ];

  @override
  Future<List<MemberModel>> getMembers() async {
    // Simulate network delay
    await Future.delayed(const Duration(milliseconds: 500));
    return _mockMembers;
  }

  @override
  Future<MemberModel> getMemberById(String id) async {
    await Future.delayed(const Duration(milliseconds: 300));
    return _mockMembers.firstWhere((m) => m.id == id);
  }

  @override
  Future<List<Relationship>> getRelationships(String memberId) async {
    await Future.delayed(const Duration(milliseconds: 300));
    return _mockRelationships.where((r) => r.memberId == memberId).toList();
  }

  @override
  Future<List<MemberModel>> searchMembers(String query) async {
    await Future.delayed(const Duration(milliseconds: 300));
    final q = query.toLowerCase();
    return _mockMembers.where((m) => m.name.toLowerCase().contains(q)).toList();
  }
}
