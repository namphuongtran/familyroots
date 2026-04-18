import 'package:flutter_bloc/flutter_bloc.dart';
import '../../../../domain/repositories/member_repository.dart';
import 'member_detail_state.dart';

/// Cubit managing a single member's detail view.
///
/// Loads member data + relationships in parallel.
class MemberDetailCubit extends Cubit<MemberDetailState> {
  final MemberRepository _repository;

  MemberDetailCubit(this._repository) : super(const MemberDetailInitial());

  /// Load a member by ID along with their relationships.
  Future<void> loadMember(String memberId) async {
    emit(const MemberDetailLoading());
    try {
      final results = await Future.wait([
        _repository.getMemberById(memberId),
        _repository.getRelationships(memberId),
      ]);
      emit(MemberDetailLoaded(
        member: results[0] as dynamic,
        relationships: results[1] as dynamic,
      ));
    } catch (e) {
      emit(MemberDetailError(e.toString()));
    }
  }
}
