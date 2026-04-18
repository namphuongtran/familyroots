import 'package:flutter/material.dart';
import '../../core/theme/app_colors.dart';

class EventCard extends StatelessWidget {
  final String title;
  final String date;
  final String description;
  final bool isLunar;
  final String lunarLabel;
  final String solarLabel;

  const EventCard({
    super.key,
    required this.title,
    required this.date,
    required this.description,
    this.isLunar = false,
    this.lunarLabel = 'Lunar',
    this.solarLabel = 'Solar',
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 260,
      margin: const EdgeInsets.only(right: 20),
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainer,
        borderRadius: BorderRadius.circular(32), // 'lg' corner radius
        boxShadow: [
          BoxShadow(
            color: AppColors.onSurface.withAlpha(15), // 6% opacity shadow
            blurRadius: 32,
            offset: const Offset(0, 8),
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
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color: AppColors.primary.withAlpha(26), // soft primary tint
                  borderRadius: BorderRadius.circular(9999), // full rounded
                ),
                child: Text(
                  isLunar ? lunarLabel : solarLabel,
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: AppColors.primary,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 0.5,
                  ),
                ),
              ),
              const Icon(Icons.event_note_outlined, color: AppColors.onSurfaceVariant, size: 20),
            ],
          ),
          const SizedBox(height: 16),
          Text(
            title,
            style: Theme.of(context).textTheme.titleLarge?.copyWith(
              color: AppColors.onSurface,
              height: 1.2,
            ),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: 8),
          Text(
            date,
            style: Theme.of(context).textTheme.labelLarge?.copyWith(
              color: AppColors.primary,
              fontWeight: FontWeight.w700,
            ),
          ),
          const Spacer(),
          Text(
            description,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: AppColors.onSurfaceVariant,
              height: 1.5,
            ),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }
}
