import requests

def test_grafana_running():
    url = 'http://localhost:3000/api/health'
    try:
        response = requests.get(url)
        assert response.status_code == 200
        print('Grafana is running and healthy.')
    except Exception as e:
        print(f'Grafana health check failed: {e}')

if __name__ == '__main__':
    test_grafana_running()
