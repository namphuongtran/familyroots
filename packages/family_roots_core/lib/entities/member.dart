import 'package:equatable/equatable.dart';

/// Domain entity representing a family member.
class MemberModel extends Equatable {
  final String id;
  final String name;
  final int generation;
  final String branch;
  final String? profileImageUrl;
  final int? birthYear;
  final int? deathYear;
  final String? biography;
  final String? gender;

  const MemberModel({
    required this.id,
    required this.name,
    required this.generation,
    required this.branch,
    this.profileImageUrl,
    this.birthYear,
    this.deathYear,
    this.biography,
    this.gender,
  });

  bool get isAlive => deathYear == null;

  /// Create from JSON (API response).
  factory MemberModel.fromJson(Map<String, dynamic> json) {
    return MemberModel(
      id: json['id'] as String,
      name: json['name'] as String,
      generation: json['generation'] as int,
      branch: json['branch'] as String,
      profileImageUrl: json['profile_image_url'] as String?,
      birthYear: json['birth_year'] as int?,
      deathYear: json['death_year'] as int?,
      biography: json['biography'] as String?,
      gender: json['gender'] as String?,
    );
  }

  /// Serialize to JSON for API requests.
  Map<String, dynamic> toJson() => {
    'id': id,
    'name': name,
    'generation': generation,
    'branch': branch,
    'profile_image_url': profileImageUrl,
    'birth_year': birthYear,
    'death_year': deathYear,
    'biography': biography,
    'gender': gender,
  };

  @override
  List<Object?> get props => [id, name, generation, branch, profileImageUrl, birthYear, deathYear, biography, gender];
}
