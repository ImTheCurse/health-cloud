const GRID_ROWS = 4;
const GRID_COLUMNS = 12;

// A recorded trace, drawn only once there is something to record.
const TRACE =
  "M0,60 L40,60 L52,58 L60,26 L68,86 L76,52 L88,60 L140,60 L152,57 L160,31 " +
  "L168,84 L176,54 L188,60 L240,60 L252,58 L260,24 L268,88 L276,53 L288,60 " +
  "L340,60 L352,57 L360,29 L368,85 L376,54 L388,60 L440,60 L452,58 L460,27 " +
  "L468,86 L476,52 L488,60 L560,60";

/**
 * The hero: an empty measurement field.
 *
 * Before consent this is flat because the database really is empty. Connecting
 * is what draws the trace, and that single draw is the only motion on the page.
 */
export default function SignalField({ recording }) {
  return (
    <svg
      className="field"
      viewBox="0 0 560 120"
      preserveAspectRatio="none"
      role="img"
      aria-label={
        recording ? "Measurements recording" : "No measurements recorded yet"
      }
    >
      <g className="field-grid">
        {Array.from({ length: GRID_ROWS - 1 }, (_, row) => {
          const y = ((row + 1) * 120) / GRID_ROWS;
          return <line key={`r${row}`} x1="0" y1={y} x2="560" y2={y} />;
        })}
        {Array.from({ length: GRID_COLUMNS - 1 }, (_, column) => {
          const x = ((column + 1) * 560) / GRID_COLUMNS;
          return <line key={`c${column}`} x1={x} y1="0" x2={x} y2="120" />;
        })}
      </g>

      <line className="field-baseline" x1="0" y1="60" x2="560" y2="60" />

      {recording && <path className="field-trace" d={TRACE} />}
    </svg>
  );
}
