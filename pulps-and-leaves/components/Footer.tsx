"use client"

import { motion } from "motion/react"

const complianceDetails = [
  { label: "GSTIN", value: "10JKIPS9038F1ZW" },
  { label: "FSSAI", value: "20426004000341" },
]

export default function Footer() {
  return (
    <footer className="bg-[#080f08] border-t border-white/8 py-16 px-6 md:px-10">
      <div className="max-w-5xl mx-auto">
        {/* WhatsApp CTA */}
        <div className="flex flex-col md:flex-row items-center justify-between gap-8 pb-12 border-b border-white/8">
          <div>
            <h3 className="text-white font-medium text-xl md:text-2xl tracking-tight">
              Questions? Chat with us directly.
            </h3>
            <p className="text-white/45 text-sm mt-2">
              We respond within minutes on WhatsApp.
            </p>
          </div>
          <motion.a
            href="https://wa.me/919999999999?text=Hi%2C%20I%27d%20like%20to%20order%20from%20Pulps%20%26%20Leaves"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2.5 text-sm font-medium text-white bg-[#25D366] px-6 py-3 rounded-full flex-shrink-0"
            whileHover={{ scale: 1.04 }}
            whileTap={{ scale: 0.97 }}
            transition={{ type: "spring", stiffness: 400, damping: 28 }}
          >
            <svg viewBox="0 0 24 24" className="w-4 h-4 fill-current" aria-hidden="true">
              <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347M12 2C6.477 2 2 6.477 2 12c0 1.89.525 3.66 1.438 5.168L2.546 21l3.924-.985A9.955 9.955 0 0012 22c5.522 0 10-4.477 10-10S17.522 2 12 2" />
            </svg>
            Chat on WhatsApp
          </motion.a>
        </div>

        {/* Links */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 py-10">
          <div>
            <div className="text-white font-medium mb-4 text-sm">Pulps &amp; Leaves</div>
            <p className="text-white/35 text-xs leading-relaxed">
              Farm-direct sourcing from Bihar and Assam.
            </p>
          </div>
          {[
            {
              heading: "Shop",
              links: ["Makhana", "Assam Tea", "Malda Mangoes", "All Products"],
            },
            {
              heading: "Company",
              links: ["Our Story", "Farm Partners", "Sustainability", "Press"],
            },
            {
              heading: "Support",
              links: ["Track Order", "Returns", "WhatsApp", "FAQ"],
            },
          ].map((col) => (
            <div key={col.heading}>
              <div className="text-white/60 text-xs font-medium tracking-widest mb-4 uppercase">
                {col.heading}
              </div>
              <ul className="space-y-2.5">
                {col.links.map((link) => (
                  <li key={link}>
                    <a
                      href="#"
                      className="text-white/35 text-xs hover:text-white/70 transition-colors duration-150"
                    >
                      {link}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="flex flex-col gap-3 py-6 border-t border-white/8">
          <div className="text-white/60 text-[11px] font-medium tracking-[0.24em] uppercase">
            Registrations
          </div>
          <div className="flex flex-col sm:flex-row sm:flex-wrap gap-2 sm:gap-3">
            {complianceDetails.map((item) => (
              <div
                key={item.label}
                className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.03] px-3 py-2 text-xs text-white/55"
              >
                <span className="text-white/35">{item.label}</span>
                <span className="font-medium tracking-[0.08em] text-white/80">{item.value}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Bottom bar */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-6 border-t border-white/8">
          <p className="text-white/25 text-xs">
            © 2025 Pulps &amp; Leaves. All rights reserved.
          </p>
          <div className="flex gap-5">
            {["Privacy", "Terms", "Shipping Policy"].map((link) => (
              <a
                key={link}
                href="#"
                className="text-white/25 text-xs hover:text-white/50 transition-colors duration-150"
              >
                {link}
              </a>
            ))}
          </div>
        </div>
      </div>
    </footer>
  )
}
