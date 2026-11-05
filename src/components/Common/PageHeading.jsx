export default function PageHeading({ title, description, children }) {
  return <header className="page-heading">
    <div><h1>{title}</h1>{description && <p>{description}</p>}</div>
    {children && <div className="action-row">{children}</div>}
  </header>;
}
