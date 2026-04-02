import 'package:equatable/equatable.dart';

class MemberModel extends Equatable {
  final String id;
  final String name;
  final int generation;
  final String branch;
  final String? profileImageUrl;

  const MemberModel({
    required this.id,
    required this.name,
    required this.generation,
    required this.branch,
    this.profileImageUrl,
  });

  @override
  List<Object?> get props => [id, name, generation, branch, profileImageUrl];
}
