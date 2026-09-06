import { useEffect } from "react";

/**
 * Track the on-screen keyboard using visualViewport.
 *
 * 100dvh cannot be used for this: in iOS standalone mode dvh stays reduced
 * after the keyboard is dismissed, leaving a dead band at the bottom of
 * the screen (spec section 13). visualViewport recovers correctly.
 */
export function useKeyboardInset(): void {
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;

    const update = () => {
      const inset = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
      document.documentElement.style.setProperty(
        "--keyboard-inset",
        `${inset}px`,
      );
    };

    update();
    vv.addEventListener("resize", update);
    vv.addEventListener("scroll", update);
    return () => {
      vv.removeEventListener("resize", update);
      vv.removeEventListener("scroll", update);
      document.documentElement.style.removeProperty("--keyboard-inset");
    };
  }, []);
}
