.PHONY: up down build verify logs test test-backend test-frontend clean

up:            ## 构建并启动前端 + 后端
	docker compose up --build -d

down:          ## 停止并移除容器
	docker compose --profile verify down

build:         ## 仅构建镜像
	docker compose build

verify:        ## 运行浏览器端到端验收（截图输出到 ./artifacts）
	docker compose --profile verify up --build --exit-code-from verify

logs:          ## 跟踪服务日志
	docker compose logs -f

test: test-backend test-frontend

test-backend:  ## 后端单元测试（需先 pip install -r backend/requirements-dev.txt）
	cd backend && python -m pytest tests/ -q

test-frontend: ## 前端单元测试（需先 npm ci）
	cd frontend && npm test

clean:
	docker compose --profile verify down -v --rmi local
	rm -rf artifacts
