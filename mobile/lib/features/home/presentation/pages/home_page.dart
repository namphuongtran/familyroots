import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../shared/l10n/app_localizations.dart';
import '../../../../shared/widgets/event_card.dart';

class HomePage extends StatelessWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);

    return Scaffold(
      backgroundColor: AppColors.background,
      body: CustomScrollView(
        slivers: [
          SliverAppBar(
            expandedHeight: 280.0,
            floating: false,
            pinned: true,
            backgroundColor: AppColors.primaryContainer,
            flexibleSpace: FlexibleSpaceBar(
              background: Stack(
                fit: StackFit.expand,
                children: [
                   Container(
                     decoration: const BoxDecoration(
                       gradient: LinearGradient(
                         begin: Alignment.topCenter,
                         end: Alignment.bottomCenter,
                         colors: [
                           AppColors.primary,
                           AppColors.primaryFixedDim,
                         ],
                       ),
                     ),
                   ),
                   Positioned(
                     bottom: -50,
                     right: -50,
                     child: Container(
                       width: 200,
                       height: 200,
                       decoration: BoxDecoration(
                         shape: BoxShape.circle,
                         color: Colors.white.withAlpha(26),
                       ),
                     ),
                   ),
                     Positioned(
                       top: 50,
                       left: -50,
                       child: Container(
                         width: 150,
                         height: 150,
                         decoration: BoxDecoration(
                           shape: BoxShape.circle,
                           color: AppColors.secondaryContainer.withAlpha(51),
                         ),
                       ),
                     ),
                   Padding(
                     padding: const EdgeInsets.fromLTRB(24, 80, 24, 24),
                     child: Column(
                       crossAxisAlignment: CrossAxisAlignment.start,
                       children: [
                         Row(
                           mainAxisAlignment: MainAxisAlignment.spaceBetween,
                           children: [
                             Text(
                               l10n.greeting,
                               style: const TextStyle(color: Colors.white70, fontSize: 16),
                             ),
                             CircleAvatar(
                               backgroundColor: Colors.white.withAlpha(51),
                               child: const Text('TV', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                             ),
                           ],
                         ),
                         const SizedBox(height: 8),
                         Text(
                           l10n.familyNameTitle('Trần Văn'),
                           style: const TextStyle(
                             color: Colors.white,
                             fontSize: 32,
                             fontWeight: FontWeight.bold,
                           ),
                         ),
                         const Spacer(),
                         // Quick Action row utilizing glassmorphism
                         ClipRRect(
                           borderRadius: BorderRadius.circular(24),
                           child: BackdropFilter(
                             filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
                             child: Container(
                               padding: const EdgeInsets.symmetric(vertical: 16),
                               decoration: BoxDecoration(
                                 color: Colors.white.withAlpha(38),
                                 borderRadius: BorderRadius.circular(24),
                               ),
                               child: Row(
                                 mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                                 children: [
                                   _buildQuickAction(Icons.search, l10n.searchAction, context, () {}),
                                   _buildQuickAction(Icons.person_add, l10n.addMemberAction, context, () => context.push('/members')),
                                   _buildQuickAction(Icons.event_available, l10n.eventsAction, context, () {}),
                                   _buildQuickAction(Icons.history_edu, l10n.genealogyAction, context, () => context.push('/tree')),
                                 ],
                               ),
                             ),
                           ),
                         )
                       ],
                     ),
                   ),
                ],
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SizedBox(height: 32),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        l10n.upcomingEvents,
                        style: Theme.of(context).textTheme.titleLarge,
                      ),
                      TextButton(
                        onPressed: () {},
                        style: TextButton.styleFrom(
                          foregroundColor: AppColors.primary,
                        ),
                        child: Text(l10n.viewAll),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),
                SizedBox(
                  height: 180,
                  child: ListView(
                    scrollDirection: Axis.horizontal,
                    padding: const EdgeInsets.symmetric(horizontal: 24),
                    children: [
                      EventCard(
                        title: 'Giỗ Tổ Dòng Họ',
                        date: 'Mùng 10/03 ÂL',
                        description: 'Họp mặt toàn thể con cháu họ Trần tại nhà thờ tổ chức lễ.',
                        isLunar: true,
                        lunarLabel: l10n.lunarCalendar,
                        solarLabel: l10n.solarCalendar,
                      ),
                      const SizedBox(width: 16),
                      EventCard(
                        title: 'Đám Cưới Minh & Lan',
                        date: '15/10/2026',
                        description: 'Lễ thành hôn của Trần Minh và Nguyễn Lan lúc 9:00 AM.',
                        isLunar: false,
                        lunarLabel: l10n.lunarCalendar,
                        solarLabel: l10n.solarCalendar,
                      ),
                      const SizedBox(width: 16),
                      EventCard(
                        title: 'Giỗ Cụ Khảo',
                        date: '12/08 ÂL',
                        description: 'Giỗ cụ Trần Khảo đời thứ 4.',
                        isLunar: true,
                        lunarLabel: l10n.lunarCalendar,
                        solarLabel: l10n.solarCalendar,
                      ),
                    ],
                  ),
                ),

                const SizedBox(height: 32),

                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  child: Text(
                    l10n.recentActivity,
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                ),
                const SizedBox(height: 16),

                // Activities List
                ListView.builder(
                  physics: const NeverScrollableScrollPhysics(),
                  shrinkWrap: true,
                  padding: const EdgeInsets.symmetric(horizontal: 24),
                  itemCount: 3,
                  itemBuilder: (context, index) {
                    return Container(
                      margin: const EdgeInsets.only(bottom: 16),
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: AppColors.surfaceContainerLowest,
                        borderRadius: BorderRadius.circular(24),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withAlpha(10),
                            blurRadius: 20,
                            offset: const Offset(0, 4),
                          )
                        ]
                      ),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Container(
                            padding: const EdgeInsets.all(12),
                            decoration: const BoxDecoration(
                              color: AppColors.primaryContainer,
                              shape: BoxShape.circle,
                            ),
                            child: const Icon(Icons.edit_document, color: AppColors.onPrimary, size: 20),
                          ),
                          const SizedBox(width: 16),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                RichText(
                                  text: TextSpan(
                                    style: Theme.of(context).textTheme.bodyMedium,
                                    children: const [
                                      TextSpan(text: 'Trần Văn Tèo ', style: TextStyle(fontWeight: FontWeight.bold, color: AppColors.primary)),
                                      TextSpan(text: 'đã cập nhật thông tin tiểu sử cho '),
                                      TextSpan(text: 'Trần Văn Tí', style: TextStyle(fontWeight: FontWeight.bold, color: AppColors.primary)),
                                    ],
                                  ),
                                ),
                                const SizedBox(height: 6),
                                Text(l10n.hoursAgo(2), style: const TextStyle(color: AppColors.textSecondary, fontSize: 13)),
                              ],
                            ),
                          ),
                        ],
                      ),
                    );
                  },
                ),
                const SizedBox(height: 40),
              ],
            ),
          )
        ],
      ),
    );
  }

  Widget _buildQuickAction(IconData icon, String label, BuildContext context, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.white.withAlpha(51),
              shape: BoxShape.circle,
            ),
            child: Icon(icon, color: Colors.white, size: 28),
          ),
          const SizedBox(height: 8),
          Text(
            label,
            style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}
