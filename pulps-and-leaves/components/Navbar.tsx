"use client"

import { useScroll, useTransform, motion } from "motion/react"

export default function Navbar() {
  const { scrollY } = useScroll()

  // motionValues passed directly to style — fully reactive
  const navBg = useTransform(scrollY, [0, 80], ["rgba(13,31,14,0)", "rgba(13,31,14,1)"])
  const blur = useTransform(scrollY, [0, 80], [0, 12])
  const borderOpacity = useTransform(scrollY, [40, 80], [0, 1])

  return (
    <motion.nav
      style={{
        backgroundColor: navBg,
        backdropFilter: blur.get() > 0 ? `blur(${blur.get()}px)` : undefined,
      }}
      className="fixed top-0 left-0 right-0 z-[100] flex justify-between items-center px-4 sm:px-6 md:px-10 py-4"
    >
      {/* Logo */}
      <span className="text-white font-medium tracking-tight text-base md:text-lg select-none">
        Pulps &amp; Leaves
      </span>

      {/* Nav links */}
      <div className="flex items-center gap-5 md:gap-8">
        {[
          { href: "#shop", label: "Shop" },
          { href: "#origins", label: "Origins" },
          { href: "#story", label: "Story" },
        ].map(({ href, label }) => (
          <a
            key={label}
            href={href}
            className="hidden sm:block text-sm text-white/70 hover:text-white transition-colors duration-200"
          >
            {label}
          </a>
        ))}

        <motion.a
          href="#shop"
          id="order-now-btn"
          className="text-sm font-medium text-white bg-[#E8A020] px-4 py-1.5 rounded-full"
          whileHover={{ scale: 1.04 }}
          whileTap={{ scale: 0.97 }}
          transition={{ type: "spring", stiffness: 400, damping: 28 }}
        >
          Order Now
        </motion.a>
      </div>

      {/* Bottom border line — fades in on scroll */}
      <motion.div
        className="absolute bottom-0 left-0 right-0 h-px bg-white/10"
        style={{ opacity: borderOpacity }}
      />
    </motion.nav>
  )
}
