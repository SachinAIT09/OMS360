import { Alert, Badge, Card, Grid, Table, Text } from "@mantine/core";
import { BarChart } from "@mantine/charts";
import { IconInfoCircle } from "@tabler/icons-react";
import { useGet } from "../api/hooks";
import type { Calibration } from "../api/types";
import { fmt } from "../lib/format";
import { Loading, SectionTitle } from "./common";

/** Does "85% confidence" come true 85% of the time? Promised vs. actual for every circuit ETR told to customers. */
export function CalibrationCard() {
  const { data } = useGet<Calibration>("/reports/calibration");
  if (!data) return <Card mb="lg"><Loading /></Card>;
  if (!data.bands.length) return null;
  const gap = data.gap_pts ?? 0;
  return (
    <Card mb="lg">
      <SectionTitle right={<Badge variant="light" color={Math.abs(gap) <= 3 ? "teal" : gap > 0 ? "orange" : "blue"}>
        {Math.abs(gap) <= 3 ? "Well calibrated" : gap > 0 ? `Overconfident by ${gap} pts` : `Underconfident by ${-gap} pts`}</Badge>}>
        Circuit ETR confidence — promised vs. actual
      </SectionTitle>
      <Grid gutter="lg">
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <BarChart h={240} data={data.bands.map(b => ({ band: b.band, Promised: b.promised_pct, Actual: b.actual_pct }))} dataKey="band"
            series={[{ name: "Promised", color: "gray.5" }, { name: "Actual", color: "teal.6" }]} unit="%" yAxisProps={{ domain: [0, 100] }} gridAxis="y" withLegend />
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Table fz="sm">
            <Table.Thead><Table.Tr><Table.Th>Confidence</Table.Th><Table.Th ta="right">ETRs</Table.Th><Table.Th ta="right">Right within ±{data.window_h} h</Table.Th><Table.Th ta="right">Mean error</Table.Th></Table.Tr></Table.Thead>
            <Table.Tbody>{data.bands.map(b => (
              <Table.Tr key={b.band}><Table.Td>{b.band}</Table.Td><Table.Td ta="right">{fmt(b.count)}</Table.Td>
                <Table.Td ta="right" fw={600} c={b.actual_pct + 5 < b.promised_pct ? "orange" : "teal"}>{b.actual_pct}%</Table.Td><Table.Td ta="right">±{b.mae_h} h</Table.Td></Table.Tr>))}
            </Table.Tbody>
          </Table>
          <Text size="xs" c="dimmed" mt="xs">Confidence means the chance the circuit is back within ±{data.window_h} h of the time customers were told.
            Measured on {fmt(data.snapshots)} circuit ETRs (every publish and every change), against when the circuit was actually restored.</Text>
        </Grid.Col>
      </Grid>
      {data.simulated_pct > 0 && <Alert mt="sm" p="xs" color="gray" icon={<IconInfoCircle size={16} />}>
        {data.simulated_pct}% of these ETRs are simulated history for the sandbox's past storms. In production this is measured on the utility's own past storms.</Alert>}
    </Card>
  );
}
