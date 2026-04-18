import 'package:flutter_bloc/flutter_bloc.dart';
import '../../../../domain/repositories/member_repository.dart';
import 'member_list_state.dart';

/// Cubit managing the member directory list.
///
/// Loads all members from the repository and supports local search filtering.
class MemberListCubit extends Cubit<MemberListState> {
  final MemberRepository _repository;

  MemberListCubit(this._repository) : super(const MemberListInitial());

  /// Load all members from repository.
  Future<void> loadMembers() async {
    emit(const MemberListLoading());
    try {
      final members = await _repository.getMembers();
      emit(MemberListLoaded(members: members, allMembers: members));
    } catch (e) {
      emit(MemberListError(e.toString()));
    }
  }

  /// Filter member list by search query.
  /// Uses the cached `allMembers` for client-side filtering.
  void searchMembers(String query) {
    final currentState = state;
    if (currentState is! MemberListLoaded) return;

    if (query.isEmpty) {
      emit(MemberListLoaded(
        members: currentState.allMembers,
        allMembers: currentState.allMembers,
      ));
      return;
    }

    final q = query.toLowerCase();
    final filtered = currentState.allMembers
        .where((m) => m.name.toLowerCase().contains(q))
        .toList();
    emit(MemberListLoaded(
      members: filtered,
      allMembers: currentState.allMembers,
    ));
  }
}
