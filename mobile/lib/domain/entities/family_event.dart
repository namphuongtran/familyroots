import 'package:equatable/equatable.dart';

/// Domain entity representing a family event (death anniversary, wedding, etc.)
class FamilyEvent extends Equatable {
  final String id;
  final String title;
  final String date;
  final String description;
  final bool isLunar;

  const FamilyEvent({
    required this.id,
    required this.title,
    required this.date,
    required this.description,
    this.isLunar = false,
  });

  factory FamilyEvent.fromJson(Map<String, dynamic> json) {
    return FamilyEvent(
      id: json['id'] as String,
      title: json['title'] as String,
      date: json['date'] as String,
      description: json['description'] as String,
      isLunar: json['is_lunar'] as bool? ?? false,
    );
  }

  Map<String, dynamic> toJson() => {
    'id': id,
    'title': title,
    'date': date,
    'description': description,
    'is_lunar': isLunar,
  };

  @override
  List<Object?> get props => [id, title, date, description, isLunar];
}
