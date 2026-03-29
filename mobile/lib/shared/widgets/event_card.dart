import 'package:flutter/material.dart';
import '../../core/theme/app_colors.dart';

class EventCard extends StatelessWidget {
  final String title;
  final String date;
  final String description;
  final bool isLunar;

  const EventCard({
    super.key,
    required this.title,
    required this.date,
    required this.description,
    this.isLunar = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 240,
      margin: const EdgeInsets.only(right: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.primary,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: AppColors.primary.withAlpha(76), // 0.3 * 255
            blurRadius: 8,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: Colors.white.withAlpha(51), // 0.2 * 255
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  isLunar ? 'Âm lịch' : 'Dương lịch',
                  style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold),
                ),
              ),
              const Icon(Icons.event, color: Colors.white70, size: 20),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            title,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 18,
              fontWeight: FontWeight.w700,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: 4),
          Text(
            date,
            style: const TextStyle(
              color: AppColors.secondaryLight,
              fontSize: 14,
              fontWeight: FontWeight.w600,
            ),
          ),
          const Spacer(),
          Text(
            description,
            style: const TextStyle(
              color: Colors.white70,
              fontSize: 12,
            ),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }
}
