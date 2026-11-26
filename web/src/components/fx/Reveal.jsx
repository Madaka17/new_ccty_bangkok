// Wraps content so it floats up once when it scrolls into view. `index` staggers siblings: the delay is
// index * 90ms (see index.css). Pass `as="li"` to keep a list's structure.
import { useReveal } from '../../lib/useReveal.js';

export default function Reveal({ as: Tag = 'div', index = 0, className = '', style, children, ...rest }) {
  const [ref, shown] = useReveal();
  return (
    <Tag ref={ref} className={`rv ${shown ? 'in' : ''} ${className}`} style={{ ...style, '--i': index }} {...rest}>
      {children}
    </Tag>
  );
}
