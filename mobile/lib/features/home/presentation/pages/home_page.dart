import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';
import 'package:google_fonts/google_fonts.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../shared/l10n/app_localizations.dart';
import '../../../../shared/widgets/event_card.dart';
import '../../../../core/di/injection.dart';
import '../bloc/event_list_cubit.dart';
import '../bloc/event_list_state.dart';

class HomePage extends StatelessWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context) {
    return BlocProvider(
      create: (_) => getIt<EventListCubit>()..loadUpcomingEvents(),
      child: const _HomeView(),
    );
  }
}

class _HomeView extends StatelessWidget {
  const _HomeView();

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);

    return Scaffold(
      backgroundColor: AppColors.background,
      body: Stack(
        children: [
          CustomScrollView(
            slivers: [
              // Welcome Hero
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(24, 100, 24, 32),
                  child: Container(
                    padding: const EdgeInsets.all(32),
                    decoration: BoxDecoration(
                      color: AppColors.surfaceContainerLow,
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: Stack(
                      children: [
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              l10n.familyNameTitle('Trần Văn'),
                              style: GoogleFonts.plusJakartaSans(
                                color: AppColors.primary,
                                fontWeight: FontWeight.bold,
                                fontSize: 24,
                              ),
                            ),
                            const SizedBox(height: 16),
                            Text(
                              'Welcome to our digital arboretum. Today is the 15th of the lunar month—a perfect time to reflect on our roots.',
                              style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                                color: AppColors.onSurfaceVariant,
                                fontWeight: FontWeight.w500,
                                height: 1.5,
                              ),
                            ),
                          ],
                        ),
                        const Positioned(
                          top: -40,
                          right: -40,
                          child: Opacity(
                            opacity: 0.1,
                            child: Icon(Icons.park_rounded, size: 160, color: AppColors.primary),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),

              // Quick Actions Grid
              SliverPadding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                sliver: SliverGrid(
                  gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 2,
                    mainAxisSpacing: 16,
                    crossAxisSpacing: 16,
                    childAspectRatio: 2.5,
                  ),
                  delegate: SliverChildListDelegate([
                    _buildHeroAction(
                      icon: Icons.person_add_rounded,
                      label: l10n.addMemberAction,
                      color: AppColors.primary,
                      onTap: () => context.push('/members'),
                    ),
                    _buildHeroAction(
                      icon: Icons.event_note_rounded,
                      label: l10n.eventsAction,
                      color: AppColors.secondaryContainer,
                      textColor: AppColors.onSecondaryContainer,
                      onTap: () {},
                    ),
                  ]),
                ),
              ),

              // Upcoming Events Section
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(24, 48, 24, 24),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        l10n.upcomingEvents,
                        style: GoogleFonts.plusJakartaSans(
                          fontWeight: FontWeight.bold,
                          fontSize: 18,
                          color: AppColors.onSurface,
                        ),
                      ),
                      TextButton(
                        onPressed: () {},
                        child: Text(
                          l10n.viewAll,
                          style: const TextStyle(color: AppColors.primary, fontWeight: FontWeight.bold),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              SliverToBoxAdapter(
                child: SizedBox(
                  height: 220,
                  child: BlocBuilder<EventListCubit, EventListState>(
                    builder: (context, state) {
                      if (state is EventListLoading) {
                        return const Center(child: CircularProgressIndicator());
                      } else if (state is EventListLoaded) {
                        return ListView.separated(
                          scrollDirection: Axis.horizontal,
                          padding: const EdgeInsets.symmetric(horizontal: 24),
                          itemCount: state.events.length,
                          separatorBuilder: (context, index) => const SizedBox(width: 20),
                          itemBuilder: (context, index) {
                            final event = state.events[index];
                            return EventCard(
                              title: event.title,
                              date: event.date,
                              description: event.description,
                              isLunar: event.isLunar,
                            );
                          },
                        );
                      }
                      return const SizedBox.shrink();
                    },
                  ),
                ),
              ),

              // Recent Updates (Timeline)
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(24, 48, 24, 24),
                  child: Text(
                    l10n.recentActivity,
                    style: GoogleFonts.plusJakartaSans(
                      fontWeight: FontWeight.bold,
                      fontSize: 18,
                      color: AppColors.onSurface,
                    ),
                  ),
                ),
              ),
              SliverPadding(
                padding: const EdgeInsets.symmetric(horizontal: 24),
                sliver: SliverList(
                  delegate: SliverChildBuilderDelegate(
                    (context, index) => _buildTimelineUpdate(context),
                    childCount: 3,
                  ),
                ),
              ),

              const SliverToBoxAdapter(child: SizedBox(height: 120)),
            ],
          ),

          // Top App Bar (Glassmorphic)
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: ClipRRect(
              child: BackdropFilter(
                filter: ui.ImageFilter.blur(sigmaX: 10, sigmaY: 10),
                child: Container(
                  height: 100,
                  padding: const EdgeInsets.fromLTRB(24, 40, 24, 0),
                  color: AppColors.background.withAlpha(204), // 80% opacity
                  child: Row(
                    children: [
                      const Icon(Icons.park_rounded, color: AppColors.primary),
                      const SizedBox(width: 12),
                      Text(
                        'The Living Archive',
                        style: GoogleFonts.plusJakartaSans(
                          fontWeight: FontWeight.w800,
                          fontSize: 18,
                          color: AppColors.primary,
                          letterSpacing: -0.5,
                        ),
                      ),
                      const Spacer(),
                      IconButton(
                        onPressed: () {},
                        icon: const Icon(Icons.search_rounded, color: AppColors.onSurfaceVariant),
                      ),
                      const CircleAvatar(
                        radius: 16,
                        backgroundImage: NetworkImage('https://lh3.googleusercontent.com/aida-public/AB6AXuCwcCKcaHBW_WQx7GZmT5n7a4nZsej9F4mMj7_cSdDUSbE5geWA1p0mgiMqml22woCGtWTcvLA1Fp3-JHAt4oW2FUkC_ROlTapDnPyQuhNbNJULQ3VrWl_dwF_1lTCnch0HLtENTOWOKEDNliyb57o0Z5vQJhJtq2jupuoQ7bLy6JFZ35frP4_saHQcoIqU0U4kocO8joJzmYpnFXnaLvrz91fYZhYYalTiearBHD0qCT3KM0MQf4zYuLu_obYNF1S6PFbYDKGMVOAV'),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () {},
        backgroundColor: AppColors.primary,
        shape: const CircleBorder(),
        elevation: 12,
        child: const Icon(Icons.add_rounded, color: Colors.white, size: 32),
      ),
    );
  }

  Widget _buildHeroAction({
    required IconData icon,
    required String label,
    required Color color,
    Color textColor = Colors.white,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(9999),
        ),
        child: Row(
          children: [
            Icon(icon, color: textColor, size: 24),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: textColor,
                  fontWeight: FontWeight.bold,
                  fontFamily: 'Plus Jakarta Sans',
                ),
              ),
            ),
            const SizedBox(width: 8),
            Icon(Icons.arrow_forward_rounded, color: textColor, size: 16),
          ],
        ),
      ),
    );
  }

  Widget _buildTimelineUpdate(BuildContext context) {
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(right: 16),
            child: Column(
              children: [
                Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(color: AppColors.background, width: 4),
                    boxShadow: [
                      BoxShadow(color: Colors.black.withAlpha(13), blurRadius: 10),
                    ],
                  ),
                  child: const CircleAvatar(
                    backgroundImage: NetworkImage('https://lh3.googleusercontent.com/aida-public/AB6AXuDdJ-dznnZ04mB7ma2qNWRj_7u6Pjy-Xfdd2Q_6PFACY9QbETwi0ymGfuUlFrloh0V9gF6ihgMUmZLIgFUK_Wx-x7fe2lVukfk8uUMUSL_H0hOyDG8qFP6e98ZT4Pg-sLQtZDW9kODqYkcb_cPWSPmUeMUeetmeOmWzSMYZXOvN3flMtH4tgSVnOH7SK_hd3dcyYPpRy_8IeXb5i74dVuCcQrGm4QYrCiKX6a_p1nhZd4byGKSbgxktJqSUgj5DU4gJo66FCCOp_Lfc'),
                  ),
                ),
                Expanded(
                  child: Container(
                    width: 1,
                    color: AppColors.outlineVariant.withAlpha(51),
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SizedBox(height: 4),
                Text.rich(
                  const TextSpan(
                    children: [
                      TextSpan(text: 'Phạm Thị Lan ', style: TextStyle(fontWeight: FontWeight.bold, color: AppColors.onSurface)),
                      TextSpan(text: 'added a new photo to '),
                      TextSpan(text: 'Memories of 1995', style: TextStyle(color: AppColors.primary, fontWeight: FontWeight.bold)),
                    ],
                  ),
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(height: 1.4),
                ),
                const SizedBox(height: 12),
                Container(
                  height: 120,
                  width: double.infinity,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(16),
                    color: AppColors.surfaceContainer,
                    image: const DecorationImage(
                      image: NetworkImage('https://lh3.googleusercontent.com/aida-public/AB6AXuDA4aFzjwENvoE-I16xl8BII9auGbp3OiNXnqgeMOK40yMCsXjEb_2pvmJkGc92eZrfYyOgQUEeeK326sEGi0Ud9_uaozaNmUmc1UUnPVjvHAoqSVCw63E_zwsmXJtjeaVGg9UvW-wciJ4YR2yMhAA_WTuzxwu_XIVWyR--ACy56jF8F_WyMtdisV_R1ImPCfNW9VlC6tvO8lHlLYkIeXZFK049pjP24d8l_qGugchyiac8HmF0Mq4QeGps7b_xvZ6i-2TzKOUSdNDm'),
                      fit: BoxFit.cover,
                    ),
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  '2 HOURS AGO',
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: AppColors.outlineVariant,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 1.0,
                  ),
                ),
                const SizedBox(height: 24),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
