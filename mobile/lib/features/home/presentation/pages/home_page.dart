import 'package:flutter/material.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../shared/widgets/event_card.dart';

class HomePage extends StatelessWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('FamilyRoots'),
        actions: [
          IconButton(
            icon: const Icon(Icons.notifications_none),
            onPressed: () {},
          ),
          const SizedBox(width: 8),
          const CircleAvatar(
            backgroundColor: AppColors.secondary,
            child: Text('TV', style: TextStyle(color: AppColors.primaryDark, fontWeight: FontWeight.bold)),
          ),
          const SizedBox(width: 16),
        ],
      ),
      body: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Welcome Header
            Container(
              padding: const EdgeInsets.all(24),
              decoration: const BoxDecoration(
                color: AppColors.primary,
                borderRadius: BorderRadius.only(
                  bottomLeft: Radius.circular(32),
                  bottomRight: Radius.circular(32),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Kính chào',
                    style: TextStyle(color: Colors.white70, fontSize: 16),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'Dòng họ Trần Văn',
                    style: TextStyle(
                      color: AppColors.secondary,
                      fontSize: 28,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(height: 24),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceAround,
                    children: [
                      _buildQuickAction(Icons.search, 'Tìm kiếm', context),
                      _buildQuickAction(Icons.person_add, 'Thêm người', context),
                      _buildQuickAction(Icons.event_available, 'Tạo sự kiện', context),
                      _buildQuickAction(Icons.history_edu, 'Gia phả', context),
                    ],
                  )
                ],
              ),
            ),
            
            const SizedBox(height: 32),

            // Upcoming Events Slider
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text(
                    'Sự Kiện Sắp Tới',
                    style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
                  ),
                  TextButton(
                    onPressed: () {},
                    child: const Text('Xem tất cả'),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            SizedBox(
              height: 160,
              child: ListView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 24),
                children: const [
                  EventCard(
                    title: 'Giỗ Tổ Dòng Họ',
                    date: 'Mùng 10/03 ÂL',
                    description: 'Họp mặt toàn thể con cháu họ Trần tại nhà thờ tổ chức lễ.',
                    isLunar: true,
                  ),
                  EventCard(
                    title: 'Đám Cưới Minh & Lan',
                    date: '15/10/2026',
                    description: 'Lễ thành hôn của Trần Minh và Nguyễn Lan lúc 9:00 AM.',
                    isLunar: false,
                  ),
                  EventCard(
                    title: 'Giỗ Cụ Khảo',
                    date: '12/08 ÂL',
                    description: 'Giỗ cụ Trần Khảo đời thứ 4.',
                    isLunar: true,
                  ),
                ],
              ),
            ),

            const SizedBox(height: 32),

            // Feed Updates
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 24),
              child: Text(
                'Hoạt Động Mới Nhất',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
              ),
            ),
            const SizedBox(height: 16),
            ListView.separated(
              physics: const NeverScrollableScrollPhysics(),
              shrinkWrap: true,
              padding: const EdgeInsets.symmetric(horizontal: 24),
              itemCount: 3,
              separatorBuilder: (context, index) => const Divider(height: 32),
              itemBuilder: (context, index) {
                return Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    CircleAvatar(
                      backgroundColor: AppColors.primary.withAlpha(26), // 0.1 * 255
                      child: const Icon(Icons.person, color: AppColors.primary),
                    ),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          RichText(
                            text: const TextSpan(
                              style: TextStyle(color: AppColors.textPrimary, fontSize: 16),
                              children: [
                                TextSpan(text: 'Trần Văn Tèo ', style: TextStyle(fontWeight: FontWeight.bold)),
                                TextSpan(text: 'đã cập nhật thông tin tiểu sử cho '),
                                TextSpan(text: 'Trần Văn Tí', style: TextStyle(fontWeight: FontWeight.bold)),
                              ],
                            ),
                          ),
                          const SizedBox(height: 4),
                          const Text('2 giờ trước', style: TextStyle(color: AppColors.textSecondary, fontSize: 12)),
                        ],
                      ),
                    ),
                  ],
                );
              },
            ),
            const SizedBox(height: 40),
          ],
        ),
      ),
    );
  }

  Widget _buildQuickAction(IconData icon, String label, BuildContext context) {
    return Column(
      children: [
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: Colors.white.withAlpha(26), // 0.1 * 255
            shape: BoxShape.circle,
          ),
          child: Icon(icon, color: Colors.white, size: 28),
        ),
        const SizedBox(height: 8),
        Text(
          label,
          style: const TextStyle(color: Colors.white, fontSize: 12),
        ),
      ],
    );
  }
}
