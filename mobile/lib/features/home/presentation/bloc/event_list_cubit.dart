import 'package:flutter_bloc/flutter_bloc.dart';
import '../../../../domain/repositories/event_repository.dart';
import 'event_list_state.dart';

/// Cubit managing the upcoming events list on the home page.
class EventListCubit extends Cubit<EventListState> {
  final EventRepository _repository;

  EventListCubit(this._repository) : super(const EventListInitial());

  /// Load upcoming events from repository.
  Future<void> loadUpcomingEvents() async {
    emit(const EventListLoading());
    try {
      final events = await _repository.getUpcomingEvents();
      emit(EventListLoaded(events));
    } catch (e) {
      emit(EventListError(e.toString()));
    }
  }
}
