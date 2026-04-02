import 'dart:ui';
import 'package:flutter/material.dart';
import '../../../../core/theme/app_colors.dart';

class FamilyTreePage extends StatefulWidget {
  const FamilyTreePage({super.key});

  @override
  State<FamilyTreePage> createState() => _FamilyTreePageState();
}

class _FamilyTreePageState extends State<FamilyTreePage> {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('Gia Phả'),
        backgroundColor: AppColors.primaryContainer,
        foregroundColor: AppColors.onPrimary,
        elevation: 0,
        actions: [
          IconButton(
            onPressed: () {},
            icon: const Icon(Icons.info_outline),
          ),
        ],
      ),
      body: Stack(
        children: [
          // Background organic shapes
          Positioned(
            top: 100,
            left: -50,
            child: Container(
              width: 300,
              height: 300,
              decoration: const BoxDecoration(
                color: AppColors.primaryFixedDim,
                shape: BoxShape.circle,
              ),
            ),
          ),
          Positioned(
            bottom: 100,
            right: -50,
            child: Container(
              width: 300,
              height: 300,
              decoration: BoxDecoration(
                color: AppColors.secondaryContainer.withAlpha(150),
                shape: BoxShape.circle,
              ),
            ),
          ),
          Positioned.fill(
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 80, sigmaY: 80),
              child: const SizedBox(),
            ),
          ),
          
          InteractiveViewer(
            constrained: false,
            boundaryMargin: const EdgeInsets.all(500),
            minScale: 0.1,
            maxScale: 2.0,
            child: SizedBox(
              width: 2000,
              height: 2000,
              child: Stack(
                children: [
                  // Root Node
                  Positioned(
                    top: 100,
                    left: 900,
                    child: _buildTreeNode('Cụ Khảo', 'Đời 1', true),
                  ),
                  
                  // Lines would go here using CustomPaint
                  
                  // Child 1
                  Positioned(
                    top: 300,
                    left: 700,
                    child: _buildTreeNode('Trần Văn A', 'Đời 2', false),
                  ),
                  
                  // Child 2
                  Positioned(
                    top: 300,
                    left: 1100,
                    child: _buildTreeNode('Trần Văn B', 'Đời 2', false),
                  ),
                ],
              ),
            ),
          ),
          
          Positioned(
            bottom: 24,
            right: 24,
            child: FloatingActionButton.extended(
              onPressed: () {},
              backgroundColor: AppColors.primary,
              foregroundColor: AppColors.onPrimary,
              icon: const Icon(Icons.add),
              label: const Text('Thêm nhánh'),
            ),
          )
        ],
      ),
    );
  }

  Widget _buildTreeNode(String name, String generation, bool isRoot) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(24),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
        child: Container(
          width: 200,
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: isRoot ? AppColors.primary.withAlpha(204) : Colors.white.withAlpha(204),
            borderRadius: BorderRadius.circular(24),
            border: Border.all(
              color: isRoot ? AppColors.primaryFixedDim : AppColors.outlineVariant,
              width: 1,
            ),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withAlpha(isRoot ? 40 : 10),
                blurRadius: 20,
                offset: const Offset(0, 8),
              ),
            ],
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              CircleAvatar(
                radius: 30,
                backgroundColor: isRoot ? AppColors.primaryFixedDim : AppColors.secondaryContainer,
                child: Icon(Icons.person, color: isRoot ? AppColors.primary : AppColors.secondary, size: 30),
              ),
              const SizedBox(height: 12),
              Text(
                name,
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  fontSize: 18,
                  color: isRoot ? Colors.white : AppColors.textPrimary,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 4),
              Text(
                generation,
                style: TextStyle(
                  fontSize: 14,
                  color: isRoot ? Colors.white70 : AppColors.textSecondary,
                ),
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
