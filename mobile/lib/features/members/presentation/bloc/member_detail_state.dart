import 'package:equatable/equatable.dart';
import '../../../../domain/entities/entities.dart';

abstract class MemberDetailState extends Equatable {
  const MemberDetailState();

  @override
  List<Object?> get props => [];
}

class MemberDetailInitial extends MemberDetailState {
  const MemberDetailInitial();
}

class MemberDetailLoading extends MemberDetailState {
  const MemberDetailLoading();
}

class MemberDetailLoaded extends MemberDetailState {
  final MemberModel member;
  final List<Relationship> relationships;

  const MemberDetailLoaded({
    required this.member,
    required this.relationships,
  });

  @override
  List<Object?> get props => [member, relationships];
}

class MemberDetailError extends MemberDetailState {
  final String message;

  const MemberDetailError(this.message);

  @override
  List<Object?> get props => [message];
}
