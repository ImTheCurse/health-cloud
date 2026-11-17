import { Component } from "react";

/**
 * Keeps a chart that throws from taking the whole page down: the card shows a
 * short message instead, and tries again when its data changes.
 */
export default class ChartBoundary extends Component {
  state = { error: null, resetKeys: this.props.resetKeys };

  static getDerivedStateFromError(error) {
    return { error };
  }

  static getDerivedStateFromProps(props, state) {
    const changed =
      props.resetKeys.length !== state.resetKeys.length ||
      props.resetKeys.some((key, index) => key !== state.resetKeys[index]);
    return changed ? { error: null, resetKeys: props.resetKeys } : null;
  }

  componentDidCatch(error) {
    console.error("A chart failed to draw:", error);
  }

  render() {
    if (this.state.error) {
      return <p className="card-state alert">This chart couldn't be drawn. Change the range or reload.</p>;
    }
    return this.props.children;
  }
}
