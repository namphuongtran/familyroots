import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';
import '../../../../core/di/injection.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../domain/entities/entities.dart';
import '../../../../shared/l10n/app_localizations.dart';
import '../bloc/member_list_cubit.dart';
import '../bloc/member_list_state.dart';

class MemberDirectoryPage extends StatelessWidget {
  const MemberDirectoryPage({super.key});

  @override
  Widget build(BuildContext context) {
    return BlocProvider(
      create: (_) => getIt<MemberListCubit>()..loadMembers(),
      child: const _MemberDirectoryView(),
    );
  }
}

class _MemberDirectoryView extends StatelessWidget {
  const _MemberDirectoryView();

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Text(l10n.membersTitle),
        backgroundColor: AppColors.primaryContainer,
        foregroundColor: AppColors.onPrimary,
        elevation: 0,
      ),
      body: Column(
        children: [
          Container(
            color: AppColors.primaryContainer,
            padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              decoration: BoxDecoration(
                color: Colors.white.withAlpha(51),
                borderRadius: BorderRadius.circular(24),
              ),
              child: TextField(
                style: const TextStyle(color: Colors.white),
                onChanged: (query) {
                  context.read<MemberListCubit>().searchMembers(query);
                },
                decoration: InputDecoration(
                  hintText: l10n.searchMembersHint,
                  hintStyle: const TextStyle(color: Colors.white70),
                  border: InputBorder.none,
                  icon: const Icon(Icons.search, color: Colors.white),
                ),
              ),
            ),
          ),
          Expanded(
            child: BlocBuilder<MemberListCubit, MemberListState>(
              builder: (context, state) {
                if (state is MemberListLoading) {
                  return const Center(
                    child: CircularProgressIndicator(color: AppColors.primary),
                  );
                }
                if (state is MemberListError) {
                  return Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.error_outline, color: AppColors.error, size: 48),
                        const SizedBox(height: 16),
                        Text(state.message, style: const TextStyle(color: AppColors.textSecondary)),
                      ],
                    ),
                  );
                }
                if (state is MemberListLoaded) {
                  if (state.members.isEmpty) {
                    return Center(
                      child: Text(
                        l10n.memberCount(0),
                        style: const TextStyle(color: AppColors.textSecondary, fontSize: 16),
                      ),
                    );
                  }
                  return ListView.separated(
                    padding: const EdgeInsets.all(24),
                    itemCount: state.members.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 16),
                    itemBuilder: (context, index) {
                      return _MemberCard(member: state.members[index]);
                    },
                  );
                }
                return const SizedBox.shrink();
              },
            ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () {},
        backgroundColor: AppColors.primary,
        child: const Icon(Icons.person_add, color: AppColors.onPrimary),
      ),
    );
  }
}

class _MemberCard extends StatelessWidget {
  final MemberModel member;

  const _MemberCard({required this.member});

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final initials = member.name.split(' ').length >= 2
        ? '${member.name.split(' ')[0][0]}${member.name.split(' ').last[0]}'
        : member.name[0];

    return GestureDetector(
      onTap: () => context.push('/member_profile/${member.id}'),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: AppColors.surfaceContainerLowest,
          borderRadius: BorderRadius.circular(24),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withAlpha(10),
              blurRadius: 20,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Row(
          children: [
            CircleAvatar(
              radius: 28,
              backgroundColor: AppColors.primaryFixedDim,
              child: Text(
                initials,
                style: const TextStyle(
                  color: AppColors.primary,
                  fontWeight: FontWeight.bold,
                  fontSize: 16,
                ),
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    member.name,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    l10n.generationBranch(member.generation, int.tryParse(member.branch) ?? 1),
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: AppColors.textSecondary,
                    ),
                  ),
                ],
              ),
            ),
            const Icon(Icons.chevron_right, color: AppColors.primary),
          ],
        ),
      ),
    );
  }
}
