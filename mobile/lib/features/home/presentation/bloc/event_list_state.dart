import 'package:equatable/equatable.dart';
import '../../../../domain/entities/entities.dart';

abstract class EventListState extends Equatable {
  const EventListState();

  @override
  List<Object?> get props => [];
}

class EventListInitial extends EventListState {
  const EventListInitial();
}

class EventListLoading extends EventListState {
  const EventListLoading();
}

class EventListLoaded extends EventListState {
  final List<FamilyEvent> events;

  const EventListLoaded(this.events);

  @override
  List<Object?> get props => [events];
}

class EventListError extends EventListState {
  final String message;

  const EventListError(this.message);

  @override
  List<Object?> get props => [message];
}
