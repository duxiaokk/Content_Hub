import { useCallback, useEffect, useState } from 'react';
import { Button, Card, List, Space, Typography, message } from 'antd';
import ReactMarkdown from 'react-markdown';
import dayjs from 'dayjs';
import { downloadDigest, generateDigest, getDigest, getDigests, triggerDailyDigest } from '../../services/api';
import type { DigestReport } from '../../types';

const { Title, Text } = Typography;

export default function PolishedDigestPage() {
  const [items, setItems] = useState<DigestReport[]>([]);
  const [selected, setSelected] = useState<DigestReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getDigests(1, 50);
      const nextItems = data.items || [];
      setItems(nextItems);
      if (nextItems.length > 0) {
        const detail = await getDigest(nextItems[0].id);
        setSelected(detail);
      } else {
        setSelected(null);
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'Failed to load digests');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSelect = async (id: number) => {
    try {
      const detail = await getDigest(id);
      setSelected(detail);
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'Failed to load digest detail');
    }
  };

  const handleGenerate = async () => {
    setActionLoading(true);
    try {
      const detail = await generateDigest();
      setSelected(detail);
      message.success('日报已生成');
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'Failed to generate digest');
    } finally {
      setActionLoading(false);
    }
  };

  const handleTrigger = async () => {
    setActionLoading(true);
    try {
      await triggerDailyDigest();
      message.success('已触发日报任务');
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'Failed to trigger digest task');
    } finally {
      setActionLoading(false);
    }
  };

  const handleDownload = async (id: number) => {
    try {
      const blob = await downloadDigest(id);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `digest_${id}.md`;
      link.click();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'Failed to download digest');
    }
  };

  return (
    <div>
      <div className="page-header">
        <div className="page-header__meta">
          <span className="page-header__eyebrow">Digest Center</span>
          <Title level={3} className="page-header__title">
            日报
          </Title>
          <Text className="page-header__description">
            浏览历史日报、预览 Markdown 内容，并支持手动触发任务、立即生成和下载。
          </Text>
        </div>
        <div className="page-header__actions">
          <Button onClick={() => void load()}>刷新</Button>
          <Button onClick={() => void handleTrigger()} loading={actionLoading}>
            触发日报任务
          </Button>
          <Button type="primary" onClick={() => void handleGenerate()} loading={actionLoading}>
            立即生成
          </Button>
        </div>
      </div>

      <div className="digest-layout">
        <Card className="surface-card detail-card" title="最新日报列表" loading={loading}>
          <List
            dataSource={items}
            renderItem={(item) => (
              <List.Item
                className={`digest-list-item ${selected?.id === item.id ? 'digest-list-item--active' : ''}`}
                actions={[
                  <Button key="download" type="link" size="small" onClick={() => void handleDownload(item.id)}>
                    下载
                  </Button>,
                ]}
                onClick={() => void handleSelect(item.id)}
              >
                <List.Item.Meta
                  title={item.title}
                  description={`${dayjs(item.generated_at || item.created_at).format('YYYY-MM-DD HH:mm:ss')} · ${item.included_count} 条`}
                />
              </List.Item>
            )}
          />
        </Card>

        <Card
          className="surface-card detail-card"
          title={selected?.title || 'Markdown 预览'}
          extra={selected ? <Button onClick={() => void handleDownload(selected.id)}>下载 Markdown</Button> : null}
        >
          {selected ? (
            <div className="markdown-content digest-preview">
              <ReactMarkdown>{selected.content_markdown}</ReactMarkdown>
            </div>
          ) : (
            <Text type="secondary">暂无日报内容</Text>
          )}
        </Card>
      </div>
    </div>
  );
}
