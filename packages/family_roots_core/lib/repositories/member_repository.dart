import '../entities/entities.dart';

/// Abstract repository contract for member operations.
/// Mobile/Web apps implement this with either Mock or real API client.
abstract class MemberRepository {
  Future<List<MemberModel>> getMembers();
  Future<MemberModel> getMemberById(String id);
  Future<List<Relationship>> getRelationships(String memberId);
  Future<List<MemberModel>> searchMembers(String query);
}
