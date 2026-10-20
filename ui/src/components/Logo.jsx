export function Mark({ size = 30 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 512 512" aria-hidden="true">
      <rect width="512" height="512" rx="112" fill="#9b1c1c" />
      <g stroke="#fff" strokeWidth="22" strokeLinecap="round" fill="none" opacity=".9">
        <path d="M256 150 L130 330 M256 150 L382 330 M130 330 L382 330" />
      </g>
      <g fill="#fff"><circle cx="256" cy="150" r="46" /><circle cx="130" cy="330" r="40" /><circle cx="382" cy="330" r="40" /></g>
      <circle cx="256" cy="150" r="18" fill="#9b1c1c" />
    </svg>
  )
}

export default function Logo({ small }) {
  return (
    <span className="flex items-center gap-2.5">
      <Mark size={small ? 22 : 30} />
      <span className={small ? 'font-display text-base font-semibold text-ink' : 'font-display text-[21px] font-semibold text-ink'}>
        Eco<span className="text-crimson-600">Mesh</span>
      </span>
    </span>
  )
}
