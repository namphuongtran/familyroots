/**
 * The wordmark at the head of the sign-in, forgot-password and reset-password screens (#201
 * moved it here from `LoginScreen`, so the three cannot drift apart). `RegisterScreen` keeps its
 * own copy.
 */
export function AuthWordmark({ subtitle }: { subtitle?: string }) {
  return (
    <div className="text-center">
      {/*
        Not copy: the product name, one literal in every locale, never a message key.
        `<wbr />` is load-bearing, not a typo: `FamilyRoots` is one unbreakable
        word, so at 320dp and 200% text scale it overflowed the `max-w-sm`
        column and scrolled the whole page sideways (T-04). A break
        opportunity is used only when the line does not fit, so the mark stays
        on one line at every normal size, and the text content stays one word.
      */}
      <h1 className="text-primary font-serif text-3xl">
        Family
        <wbr />
        Roots
      </h1>
      {subtitle && <p className="text-muted-foreground mt-1 text-sm">{subtitle}</p>}
    </div>
  )
}
