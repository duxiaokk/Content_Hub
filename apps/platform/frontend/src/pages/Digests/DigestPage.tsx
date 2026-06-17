import { useCallback, useEffect, useState } from 'react';
import { Button, Card, List, Space, Typography, message } from 'antd';
import ReactMarkdown from 'react-markdown';
import dayjs from 'dayjs';
import { downloadDigest, generateDigest, getDigest, getDigests, triggerDailyDigest } from '../../services/api';
import type { DigestReport } from '../../types';

const { Title, Text } = Typography;

export default function DigestPage() {
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
      message.error(error instanceof Error ? error.message : '加载日报失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleSelect = async (id: number) => {
    try {
      const detail = await getDigest(id);
      setSelected(detail);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载日报详情失败');
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
      message.error(error instanceof Error ? error.message : '生成日报失败');
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
      message.error(error instanceof Error ? error.message : '触发日报任务失败');
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
      message.error(error instanceof Error ? error.message : '下载日报失败');
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            日报
          </Title>
          <Text type="secondary">查看历史日报、预览 Markdown，并支持手动生成与下载。</Text>
        </div>
        <Space>
          <Button onClick={load}>刷新</Button>
          <Button onClick={handleTrigger} loading={actionLoading}>
            触发日报任务
          </Button>
          <Button type="primary" onClick={handleGenerate} loading={actionLoading}>
            立即生成
          </Button>
        </Space>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: 16, alignItems: 'start' }}>
        <Card title="最新日报列表" loading={loading}>
          <List
            dataSource={items}
            renderItem={(item) => (
              <List.Item
                style={{ cursor: 'pointer', paddingInline: 0 }}
                actions={[
                  <Button key="download" type="link" size="small" onClick={() => handleDownload(item.id)}>
                    下载
                  </Button>,
                ]}
                onClick={() => handleSelect(item.id)}
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
          title={selected?.title || 'Markdown 预览'}
          extra={selected ? <Button onClick={() => handleDownload(selected.id)}>下载 Markdown</Button> : null}
        >
          {selected ? (
            <div style={{ minHeight: 480 }}>
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
