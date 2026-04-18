import 'package:equatable/equatable.dart';
import '../../../../domain/entities/entities.dart';

abstract class MemberListState extends Equatable {
  const MemberListState();

  @override
  List<Object?> get props => [];
}

class MemberListInitial extends MemberListState {
  const MemberListInitial();
}

class MemberListLoading extends MemberListState {
  const MemberListLoading();
}

class MemberListLoaded extends MemberListState {
  final List<MemberModel> members;
  final List<MemberModel> allMembers; // kept for search/filter reset

  const MemberListLoaded({
    required this.members,
    required this.allMembers,
  });

  @override
  List<Object?> get props => [members, allMembers];
}

class MemberListError extends MemberListState {
  final String message;

  const MemberListError(this.message);

  @override
  List<Object?> get props => [message];
}
