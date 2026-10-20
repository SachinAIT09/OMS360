import { useNavigate, useParams } from "react-router-dom";
import { Button, Group } from "@mantine/core";
import { IconArrowLeft } from "@tabler/icons-react";
import { AssetDetailView } from "../components/AssetDetail";

/** /asset/:id — the same record wherever a unit is opened from (map, tables, circuit drawer, assistant). */
export default function AssetDetailPage() {
  const { id = "" } = useParams();
  const go = useNavigate();
  return (
    <>
      <Group mb="sm"><Button variant="subtle" size="xs" leftSection={<IconArrowLeft size={14} />} onClick={() => go(-1)}>Back</Button></Group>
      <AssetDetailView id={decodeURIComponent(id)} />
    </>
  );
}
