# Flutter Development & Testing Lessons Learned

This document tracks important lessons learned during Flutter development and widget testing within the FamilyRoots platform to prevent regressions and common setup pitfalls.

## 1. Widget Testing: `BlocProvider` and Dependency Injection
**Context:** When testing pages that depend on Cubits or BLoCs, simply registering the mock via `GetIt` might not be enough. If the targeted page relies on a `BlocProvider` that is normally wrapped by a parent router (e.g., GoRouter) or by its own structure, you will encounter `ProviderNotFoundException` during tests if it's not mirrored in the mock setup or the page itself.

**Lesson:** 
- **Correct Page Implementation:** Consistently wrap views directly in the page file if they are page-level BLoCs. For example, `HomePage` should wrap `_HomeView` with a `BlocProvider(create: (_) => getIt<EventListCubit>())`. 
- **Test Implementation:** Any test piping the widget must ensure that the `BlocProvider` exists in the element tree. By having the Page itself construct the `BlocProvider` via `GetIt`, the tests only need to swap the `GetIt` instance for a mock.

## 2. Widget Testing: Fixing Modern Layout Bounds (`tester.view`)
**Context:** Older tutorials and StackOverflow answers often suggest setting test window sizes via `tester.binding.window.physicalSizeTestValue`. In modern Flutter, this is deprecated and throws analysis errors.

**Lesson:**
Always use `tester.view` for defining physical dimensions and pixel ratios inside `testWidgets`. Also, ensure you reset them immediately via `addTearDown` to not pollute other tests.
```dart
tester.view.physicalSize = const Size(1080, 2400);
tester.view.devicePixelRatio = 2.0;
addTearDown(() => tester.view.resetPhysicalSize());
addTearDown(() => tester.view.resetDevicePixelRatio());
```

## 3. Dealing with `RenderFlex` Overflows in `SliverAppBar` and `CustomScrollView`
**Context:** When embedding widgets containing `Column` layout inside a `FlexibleSpaceBar` (which changes its size as it collapses), unbounded elements inside the flexible space will overflow violently and crash both the app and test cases.

**Lesson:**
- **Never use `Expanded` or `Spacer` inside a `FlexibleSpaceBar` background** unless wrapped in a strictly bounded height container.
- If you have an arbitrary column of content in the `SliverAppBar` background, wrap the `Column` inside a `SingleChildScrollView(physics: const NeverScrollableScrollPhysics())`. This prevents the flex properties from rejecting bounding constraints when the sliver shrinks, allowing it to seamlessly clip or wrap natively instead of throwing *RenderFlex children have non-zero flex but incoming height constraints are unbounded*.
