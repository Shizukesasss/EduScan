export default function AccountAvatar({ className = 'account-avatar', name, picture, initials, alt = '' }) {
  const fallback = initials || name?.trim().charAt(0).toUpperCase() || 'U';
  return <span className={`${className} profile-avatar`} aria-hidden={alt ? undefined : true}>
    {picture ? <img src={picture} alt={alt} /> : fallback}
  </span>;
}
