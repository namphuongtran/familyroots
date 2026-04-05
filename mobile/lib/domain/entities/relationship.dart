import 'package:equatable/equatable.dart';

/// Domain entity representing a family relationship.
class Relationship extends Equatable {
  final String memberId;
  final String relatedMemberId;
  final String relationType; // father, mother, wife, husband, son, daughter
  final String relatedMemberName;

  const Relationship({
    required this.memberId,
    required this.relatedMemberId,
    required this.relationType,
    required this.relatedMemberName,
  });

  factory Relationship.fromJson(Map<String, dynamic> json) {
    return Relationship(
      memberId: json['member_id'] as String,
      relatedMemberId: json['related_member_id'] as String,
      relationType: json['relation_type'] as String,
      relatedMemberName: json['related_member_name'] as String,
    );
  }

  Map<String, dynamic> toJson() => {
    'member_id': memberId,
    'related_member_id': relatedMemberId,
    'relation_type': relationType,
    'related_member_name': relatedMemberName,
  };

  @override
  List<Object?> get props => [memberId, relatedMemberId, relationType, relatedMemberName];
}
